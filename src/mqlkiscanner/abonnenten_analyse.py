"""Explicit one-click research run: Top 200/source, floating DD, short KI, Top 5.

These results deliberately do not overwrite the three-month workflow verdicts.
Only an explicit start/resume performs network calls or terminal work.
"""
from __future__ import annotations

import math
import os
import uuid
from copy import deepcopy
from collections import Counter

from . import config, db, ingest, quellen as source_registry, scan_worker
from .abonnenten_analyse_store import Store, now
from .abonnenten_analyse_ki import AnalyseKI, Angehalten, FACTS_PAYLOAD_VERSION, digest, report_pdf
from .analysis_version import FORENSICS_VERSION
from .llm import prompts
from .llm.client import LlmBudgetError, LlmError, LlmNoBalanceError

POLICY_VERSION = "abonnenten_recherche_v1"
BUDGET_SETTING_KEYS = frozenset({
    "llm_max_total_tokens", "agenten_tagesbudget_tokens", "agenten_monatsbudget_tokens",
})
KI_CONFIG_RESTART_FIELD = "ki_config_restart_checkpoint"
_FINISHED_DATA_ATTEMPTS = frozenset({
    "datenluecke", "ki_offen", "ki_fehler", "fertig", "ausgeschlossen", "nicht_geeignet", "quellenwerte",
})


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def percentile(values: dict) -> dict:
    """Midrank percentiles, ties including singleton/all-equal groups = 50."""
    valid = {key: float(value) for key, value in values.items() if _finite(value)}
    counts, below, mapping = Counter(valid.values()), 0, {}
    for value in sorted(counts):
        mapping[value] = 100.0 * (below + .5 * counts[value]) / len(valid)
        below += counts[value]
    return {key: mapping[value] for key, value in valid.items()}


def rank_entries(entries: list[dict], weight: float = 70) -> list[dict]:
    candidates = [e for e in entries if e.get("eligible") and _finite(e.get("retdd_jahr"))
                  and e["retdd_jahr"] > 0 and _finite(e.get("abo_perzentil"))
                  and not e.get("review_pending")]
    efficiency = percentile({e["signal_ref"]: e["retdd_jahr"] for e in candidates})
    for entry in entries:
        entry["rang"] = entry["auswahlwert"] = entry["retdd_perzentil"] = None
    for entry in candidates:
        entry["retdd_perzentil"] = efficiency[entry["signal_ref"]]
        entry["auswahlwert"] = weight / 100 * entry["retdd_perzentil"] + (1-weight / 100) * entry["abo_perzentil"]
    candidates.sort(key=lambda e: (-e["auswahlwert"], -e["retdd_jahr"], -(e.get("dauer_monate") or 0),
                                    str(e.get("quellen_uid") or e["quelle"]), e["id"]))
    for index, entry in enumerate(candidates, 1):
        entry["rang"] = index
    return candidates


def _profile(run: dict) -> dict:
    return {"policy_version": POLICY_VERSION, "min_monate": 2, "min_trades": 50,
            "retdd_definition": "Jahres-CAGR / maximaler gemessener relativer Equity-DD inklusive Floating",
            "dd_grenze": run["dd_grenze"], "retdd_gewicht": run["retdd_gewicht"],
            "abonnenten_gewicht": 100-run["retdd_gewicht"], "top_n_je_quelle": 200,
            "min_abonnenten": 1, "messbasis": "Historisches Exportfenster; H1-Schlüsse, keine Intrabar-Tiefs; aktueller offener Bestand nicht belegt"}


def _arbeitsreihenfolge(entries: list[dict], sources: list[str]) -> list[dict]:
    """Only schedule work; membership and the ranking formula stay unchanged."""
    priority = {source: index for index, source in enumerate(sources)}
    return sorted(entries, key=lambda entry: (
        priority.get(entry.get("quelle"), len(priority)), str(entry.get("quelle") or ""),
        -(entry["abonnenten"] if _finite(entry.get("abonnenten")) else -1),
        entry["id"], entry["signal_ref"]))


def _alive(run):
    if run.get("status") != "laeuft":
        return False
    active = scan_worker.active_run()
    if active is not None and active.workflow.get("abonnenten_id") == run["id"]:
        return True
    if run.get("pid") == os.getpid():
        return False
    try:
        import psutil
        return abs(psutil.Process(run["pid"]).create_time()-run.get("process_start", 0)) < 1
    except Exception:
        return False


def zustand(run_id=None) -> dict:
    store = Store()
    run = store.read(run_id)
    if not run:
        return {}
    entries = store.tasks(run["id"])
    run["entries"] = sorted(entries, key=lambda e: (e.get("rang") or 10**9, e.get("quelle", ""), e.get("name", "")))
    run["laeuft"] = _alive(run)
    if run["status"] == "laeuft" and not run["laeuft"]:
        run["status"] = "unterbrochen"
        run["detail"] = "Workerprozess beendet; gespeicherte Stufen können fortgesetzt werden."
    run["total"] = len(entries)
    run["done"] = sum(e.get("status") in {"fertig", "ausgeschlossen", "datenluecke", "nicht_geeignet", "quellenwerte"} for e in entries)
    run["tokens"] = store.spent(run["id"])
    return run


def laeufe() -> list[dict]:
    return [{k: row.get(k) for k in ("id", "status", "created_at", "quellen", "retdd_gewicht", "dd_grenze")}
            for row in Store().runs()]


def starten(quellen: list[str], settings=None, retdd_gewicht=70, dd_grenze=None) -> str:
    if not _finite(retdd_gewicht) or not 0 <= retdd_gewicht <= 100:
        raise ValueError("RetDD-Gewicht muss zwischen 0 und 100 liegen")
    if dd_grenze is not None and (not _finite(dd_grenze) or dd_grenze <= 0):
        raise ValueError("Die optionale DD-Grenze muss positiv sein")
    active = db.list_quellen(nur_aktiv=True)
    chosen = {db.kanonische_quelle(q) for q in quellen}
    if not chosen or chosen - {db.kanonische_quelle(q["kuerzel"]) for q in active}:
        raise ValueError("Mindestens eine gültige aktive Quelle auswählen")
    missing = prompts.fehlende_vorlagen(prompts.ABONNENTEN_PROMPT_KEYS)
    if missing:
        raise ValueError("Berichtsvorlagen fehlen: " + ", ".join(missing))
    run_id = uuid.uuid4().hex
    run = {"id": run_id, "created_at": now(), "updated_at": now(), "status": "geplant", "phase": "geplant",
           "quellen": sorted(chosen), "retdd_gewicht": float(retdd_gewicht), "dd_grenze": dd_grenze,
           "policy_version": POLICY_VERSION, "logs": [], "detail": "Bewertung wird gestartet",
           "snapshot_quellen": {}, "stop_requested": False, "fehler": ""}
    store = Store()
    store.create(run)
    try:
        _launch(run_id, settings)
    except Exception as exc:
        store.update(run_id, status="fehlgeschlagen", fehler=str(exc))
        raise
    return run_id


def fortsetzen(run_id: str) -> bool:
    run = Store().read(run_id)
    if not run:
        raise ValueError("Unbekannter Bewertungslauf")
    if _alive(run):
        return False
    _launch(run_id)
    return True


def stoppen(run_id=None) -> None:
    store = Store()
    run = store.read(run_id)
    if run:
        store.update(run["id"], stop_requested=True)


def _budget_settings(run: dict) -> dict:
    """Only this run's explicitly persisted positive integer budget overrides."""
    overrides = run.get("budget_settings", {})
    if not isinstance(overrides, dict):
        raise ValueError("budget_settings des Recherchelaufs muss ein Objekt sein")
    approved = {}
    for key in BUDGET_SETTING_KEYS:
        if key not in overrides:
            continue
        value = overrides[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"budget_settings.{key} muss eine positive ganze Zahl sein")
        approved[key] = value
    return approved


def _budget_attempt_reusable(entry: dict, refs: set[int], basis: str) -> bool:
    """Explicit one-time budget restart may retain a finished failed attempt."""
    if (entry.get("signal_ref") not in refs or entry.get("data_basis") != basis
            or entry.get("abgebrochen") is True or entry.get("status") not in {
                "datenluecke", "ki_offen", "fertig", "ausgeschlossen", "nicht_geeignet", "quellenwerte"}):
        return False
    path, sha = entry.get("trades_path"), entry.get("trades_sha256")
    if bool(path) != bool(sha):
        return False
    if path:
        if not isinstance(path, str) or not isinstance(sha, str):
            return False
        try:
            db.verify_trade_file(path, sha)
        except (OSError, ValueError, TypeError):
            return False
    return True


def _restart_exclusions():
    from .signal_identity import identity_key
    return {identity_key(item): item for item in config.load_known_signals().get("ausgeschlossen", [])}


def _restart_run_basis(run):
    return digest({"id": run.get("id"), "quellen": run.get("quellen"),
                   "policy_version": run.get("policy_version"), "profile": _profile(run)})


def _restart_tasks(run, entries, settings):
    """Validate every completed data attempt, including explicit data gaps."""
    if not isinstance(entries, list) or not entries:
        raise ValueError("KI-Konfigurationsneustart: keine abgeschlossenen Datenversuche")
    sources = run.get("quellen")
    if (not isinstance(sources, list) or not sources or any(not isinstance(q, str) or not q for q in sources)
            or len(set(sources)) != len(sources)):
        raise ValueError("KI-Konfigurationsneustart: ungültige Quellenliste")
    common, exclusions = daten_basis(settings), _restart_exclusions()
    refs, owners = set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("KI-Konfigurationsneustart: ungültiger Datenversuch")
        ref, provider_id, uid = entry.get("signal_ref"), entry.get("id"), entry.get("quellen_uid")
        if (isinstance(ref, bool) or not isinstance(ref, int) or ref <= 0 or ref in refs
                or isinstance(provider_id, bool) or not isinstance(provider_id, int) or provider_id <= 0
                or not isinstance(uid, str) or not uid or entry.get("quelle") not in sources):
            raise ValueError("KI-Konfigurationsneustart: ungültige oder doppelte Quellenidentität")
        owner = (uid, provider_id)
        if owner in owners:
            raise ValueError("KI-Konfigurationsneustart: doppelte Anbieteridentität")
        refs.add(ref)
        owners.add(owner)
        if entry.get("status") not in _FINISHED_DATA_ATTEMPTS or entry.get("abgebrochen") is True:
            raise ValueError(f"KI-Konfigurationsneustart: Datenversuch {ref} ist nicht abgeschlossen")
        if entry.get("data_basis") != eintrag_basis(entry, common, exclusions):
            raise ValueError(f"KI-Konfigurationsneustart: Bewertungsbasis für {ref} verändert")
        path, sha = entry.get("trades_path"), entry.get("trades_sha256")
        if bool(path) != bool(sha):
            raise ValueError(f"KI-Konfigurationsneustart: unvollständiger Trade-Snapshot für {ref}")
        if path:
            if not isinstance(path, str) or not isinstance(sha, str):
                raise ValueError(f"KI-Konfigurationsneustart: ungültiger Trade-Snapshot für {ref}")
            try:
                db.verify_trade_file(path, sha)
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(f"KI-Konfigurationsneustart: Trade-Snapshot für {ref} nicht belegt: {exc}") from exc
        elif entry.get("data_done") and not (entry.get("quelle") == "robo"
                                              and entry.get("auswertung_typ") == "quellenprofitabilitaet"):
            raise ValueError(f"KI-Konfigurationsneustart: fertige Daten ohne Trade-Snapshot für {ref}")
    return sorted(entries, key=lambda entry: entry["signal_ref"])


def _restart_process_alive(run):
    """Preparation must not mistake a paused status for a terminated worker."""
    active = scan_worker.active_run()
    if active is not None and active.workflow.get("abonnenten_id") == run.get("id"):
        return True
    pid = run.get("pid")
    if pid is None:
        return False
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or not _finite(run.get("process_start")):
        raise ValueError("KI-Konfigurationsneustart: Workerprozess nicht eindeutig prüfbar")
    import psutil
    try:
        return abs(psutil.Process(pid).create_time() - run["process_start"]) < 1
    except psutil.NoSuchProcess:
        return False
    except psutil.Error as exc:
        raise ValueError("KI-Konfigurationsneustart: Workerende nicht nachweisbar") from exc


def prepare_ki_config_restart_checkpoint(run: dict, entries: list[dict], settings: dict, *, prepared_at=None) -> dict:
    """Return an explicit one-use checkpoint; never write storage or start work.

    The caller persists this only after cooperative stop and actual worker exit.
    Source failures and completed failed data attempts are retained verbatim.
    """
    if run.get("status") != "angehalten" or _restart_process_alive(run):
        raise ValueError("KI-Konfigurationsneustart benötigt einen angehaltenen und beendeten Worker")
    if not isinstance(run.get("id"), str) or not run["id"]:
        raise ValueError("KI-Konfigurationsneustart: ungültige Laufidentität")
    if not isinstance(run.get("snapshot_quellen"), dict):
        raise ValueError("KI-Konfigurationsneustart: Quellensnapshot fehlt")
    tasks = _restart_tasks(run, entries, settings)
    timestamp = prepared_at if prepared_at is not None else now()
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("KI-Konfigurationsneustart: Vorbereitungszeit fehlt")
    return {"version": 1, "purpose": "ki_configuration_restart", "state": "prepared",
            "run_id": run["id"], "prepared_at": timestamp,
            "run_basis_sha256": _restart_run_basis(run),
            "source_snapshot_sha256": digest(run["snapshot_quellen"]),
            "task_snapshot_sha256": digest(tasks), "refs": [entry["signal_ref"] for entry in tasks]}


def _validate_ki_config_restart(run, entries, settings):
    if KI_CONFIG_RESTART_FIELD not in run:
        return None
    checkpoint = run[KI_CONFIG_RESTART_FIELD]
    if not isinstance(checkpoint, dict):
        raise ValueError("KI-Konfigurationsneustart: Checkpoint muss ein Objekt sein")
    if (type(checkpoint.get("version")) is not int or checkpoint["version"] != 1
            or checkpoint.get("purpose") != "ki_configuration_restart"
            or checkpoint.get("run_id") != run.get("id")
            or not isinstance(checkpoint.get("prepared_at"), str) or not checkpoint["prepared_at"].strip()):
        raise ValueError("KI-Konfigurationsneustart: ungültiger oder fremder Checkpoint")
    if checkpoint.get("state") == "consumed":
        return None  # Retain the audit; this permission cannot be used twice.
    if checkpoint.get("state") != "prepared" or run.get("status") != "angehalten":
        raise ValueError("KI-Konfigurationsneustart: ungültiger oder fremder Checkpoint")
    tasks = _restart_tasks(run, entries, settings)
    expected = {"run_basis_sha256": _restart_run_basis(run),
                "source_snapshot_sha256": digest(run.get("snapshot_quellen")),
                "task_snapshot_sha256": digest(tasks), "refs": [entry["signal_ref"] for entry in tasks]}
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise ValueError("KI-Konfigurationsneustart: Lauf, Quellensnapshot oder Aufgaben seit Vorbereitung verändert")
    return checkpoint


def kurztest_basis(entry: dict, profile: dict, settings: dict) -> str:
    """Pure fingerprint shared by normal execution and an explicit KI probe."""
    return digest({"data": entry.get("data_basis"), "sha": entry.get("trades_sha256"),
                   "facts_payload_version": FACTS_PAYLOAD_VERSION,
                   "facts": entry.get("forensik"), "equity": entry.get("equity"), "profile": profile,
                   **({"auswahl_luecken": entry.get("abo_ausgelassene_positionen")}
                      if entry.get("abo_referenz_vollstaendig") is False else {}),
                   "prompt": prompts.prompt_fingerprint(("abonnenten_kurztest",)),
                   "model": prompts.prompt_model("abonnenten_kurztest", settings)})


def _launch(run_id, settings=None):
    store = Store()
    run = store.read(run_id)
    if not run:
        raise ValueError("Unbekannter Bewertungslauf")
    overrides = _budget_settings(run)  # validate before creating any worker
    settings = {**config.load_settings(), **(settings or {}), **overrides}
    def execute():
        _execute(store, run_id, settings)
    worker = scan_worker.start(execute, workflow={"abonnenten_id": run_id}, control={}, logs={}, results=[],
                               lock_basis=config.DATA_DIR)
    if worker is None:
        raise RuntimeError("Ein anderer Prüf- oder Studienlauf arbeitet bereits")


def _snapshot(store, run, settings, log, stopped):
    from . import client_updates
    sources = {db.kanonische_quelle(q["kuerzel"]): q for q in db.list_quellen(nur_aktiv=True)}
    done = dict(run.get("snapshot_quellen") or {})
    pending = [q for q in run["quellen"] if done.get(q, {}).get("status") != "fertig"]
    if not pending:
        return
    store.update(run["id"], phase="quellen_aktualisieren")
    updates = client_updates.starte_alle_updates(
        {**settings, "update_ziel_signale": 200}, log=log, gestopft=stopped,
        tradelisten=False, katalog_max_alter_h=0, quellen_filter=pending, modus="abonnenten")
    for name in pending:
        if stopped():
            raise Angehalten("Stop angefordert")
        source = sources.get(name)
        update = updates.get(name) or {}
        coverage = update.get("abonnenten_katalog") or {}
        partial_catalog = (update.get("status") == client_updates.TEILWEISE
                           and coverage.get("complete") is False
                           and coverage.get("reached_end") is True
                           and bool(coverage.get("skipped_positions"))
                           and not update.get("tradelisten_fehler")
                           and not update.get("tradelisten_abgebrochen"))
        if source is None or (update.get("status") != client_updates.FERTIG and not partial_catalog):
            reason = update.get("fehler") or update.get("detail") or "Keine aktuelle aktive Quelle verfügbar"
            done[name] = {"status": "fehler", "grund": str(reason)}
            log(f"Quelle {name}: {reason}")
            store.update(run["id"], snapshot_quellen=done)
            continue
        try:
            cli = source_registry.client_fuer_quelle(source)
            health = cli.health()
            raw = ingest.hole_katalog(source, client=cli, min_subscribers=1)
            candidates = ingest.kandidaten(source, raw)
            claims = {}
            for entry in candidates:
                claims.setdefault(entry["id"], set()).add(entry["quelle_version"])
            if any(len(versions) > 1 for versions in claims.values()):
                raise ValueError("Widersprüchliche Plattformen für dieselbe Quellenidentität")
            valid = [e for e in candidates if isinstance(e.get("abonnenten"), int) and e["abonnenten"] >= 1]
            if len(valid) != len(candidates):
                raise ValueError("Positive Katalogauswahl enthält fehlende/ungültige Abonnentenzahlen")
            valid.sort(key=lambda e: (-e["abonnenten"], e["id"]))
            valid = valid[:200]
            popularity = percentile({e["id"]: e["abonnenten"] for e in valid})
            for entry in valid:
                if not entry["platform"] and not (name == "robo" and entry["quelle_version"] == "rst"):
                    raise ValueError("Unbekannte Plattform im aktuellen Katalog")
                identity = db.resolve_identity(entry["id"], quelle=name, create=True)
                entry.update(signal_ref=identity.signal_ref, quelle=name, quellen_uid=identity.quellen_uid,
                             abo_perzentil=popularity[entry["id"]], abo_referenz_n=len(valid),
                             katalog_stand=now(), status="wartet", grund="", data_done=False)
                if coverage:
                    entry.update(abo_referenz_vollstaendig=coverage["complete"],
                                 abo_ausgelassene_positionen=coverage["skipped_positions"],
                                 abo_katalog_geprueft=coverage["scanned_providers"])
                if health.get("providerRefresh") is not True:
                    entry["quellen_hinweis"] = health.get("providerRefreshReason") or "Gezielter Anbieterabruf benötigt einen aktualisierten Client"
            checkpoint = {"status": "fertig", "anzahl": len(valid), "stand": now(), "update_job": update.get("job_id")}
            if coverage:
                checkpoint["abonnenten_katalog"] = coverage
            done = store.freeze_source(run["id"], name, valid, checkpoint)
            log(f"{name}: {len(valid)} Anbieter im Prüfauftrag festgeschrieben")
            if partial_catalog:
                log(f"{name}: Auswahl aus lesbaren Anbietern; "
                    f"{len(coverage['skipped_positions'])} API-Position(en) ausgelassen.")
        except Exception as exc:
            done[name] = {"status": "fehler", "grund": str(exc)}
            log(f"Quelle {name}: {exc}")
        store.update(run["id"], snapshot_quellen=done)


def _execute(store, run_id, settings):
    from .abonnenten_analyse_daten import AnalyseDaten
    run = store.read(run_id)
    log = lambda message: store.log(run_id, message)
    stopped = lambda: bool(store.read(run_id).get("stop_requested"))
    try:
        # This controlled restart validates all frozen data before any source
        # refresh, terminal provider construction or paid model operation.
        frozen_entries = store.tasks(run_id)
        checkpoint = _validate_ki_config_restart(run, frozen_entries, settings)
        try:
            import psutil
            process_start = psutil.Process().create_time()
        except ImportError:
            process_start = 0
        store.update(run_id, status="laeuft", pid=os.getpid(), process_start=process_start,
                     stop_requested=False, fehler="", phase="kurzanalysen" if checkpoint is not None else "quellen_aktualisieren",
                     budget_applied={key: settings[key] for key in BUDGET_SETTING_KEYS if key in settings})
        if checkpoint is None:
            _snapshot(store, run, settings, log, stopped)
            run = store.read(run_id)
        profile = _profile(run)
        entries = _arbeitsreihenfolge(frozen_entries if checkpoint is not None else store.tasks(run_id), run["quellen"])
        data_basis = daten_basis(settings)
        from .signal_identity import identity_key
        exclusions = {identity_key(item): item for item in config.load_known_signals().get("ausgeschlossen", [])}
        raw_refs = run.get("budget_resume_refs", [])
        budget_refs = ({ref for ref in raw_refs if isinstance(ref, int) and not isinstance(ref, bool) and ref > 0}
                       if isinstance(raw_refs, list) else set())
        if checkpoint is not None:
            store.update(run_id, **{KI_CONFIG_RESTART_FIELD: {
                **checkpoint, "state": "consumed", "consumed_at": now()}})
            log(f"KI-Konfigurationsneustart: {len(entries)} abgeschlossene Datenversuche erhalten; "
                "Quellensnapshot und Datenlücken bleiben unverändert.")
        else:
            with AnalyseDaten(settings, log=log) as provider:
                store.update(run_id, phase="trades_und_equity")
                for entry in entries:
                    if stopped():
                        raise Angehalten("Stop angefordert")
                    entry_basis = eintrag_basis(entry, data_basis, exclusions)
                    if _budget_attempt_reusable(entry, budget_refs, entry_basis):
                        log(f"Budgetfortsetzung: gespeicherten Datenversuch für {entry['name']} erhalten; "
                            "vorhandene Datenlücken bleiben unverändert.")
                        continue
                    if entry.get("data_done") and entry.get("data_basis") == entry_basis:
                        if entry.get("auswertung_typ") == "quellenprofitabilitaet":
                            continue  # Persistierte Quellenwerte brauchen keinen Trade-Snapshot.
                        try:
                            db.verify_trade_file(entry["trades_path"], entry["trades_sha256"])
                            continue
                        except (OSError, ValueError, KeyError) as exc:
                            log(f"Snapshot für {entry['name']} nicht mehr belegt; neu beschaffen: {exc}")
                    if entry.get("kurztest") or entry.get("bericht_markdown"):
                        entry.setdefault("previous_results", []).append({k: entry.get(k) for k in (
                            "trades_sha256", "data_basis", "kurztest", "kurz_basis", "bericht_markdown",
                            "top5_basis", "top5_befund", "pdf_path", "retdd_jahr", "equity_dd_pct",
                            "review_pending", "ki_pruefhinweise", "ki_pruefhinweis_quellen", "ki_hinweisstatus")})
                        for key in ("kurztest", "kurz_basis", "bericht_markdown", "top5_basis", "pdf_path",
                                    "review_pending", "ki_pruefhinweise", "ki_pruefhinweis_quellen",
                                    "ki_hinweisstatus", "top5_befund"):
                            entry.pop(key, None)
                    # An earlier attempt's cancellation is not a property of
                    # this new attempt. A current cancellation result sets it
                    # back to True; a crash remains visibly status=rechnet.
                    entry.update(status="rechnet", grund="", data_done=False, abgebrochen=False)
                    store.save_task(run_id, entry)
                    log(f"Trades und Equity: {entry['quelle']} · {entry['name']}")
                    try:
                        result = provider.berechne(entry, should_stop=stopped)
                        entry.update(result)
                        entry.update(data_done=bool(result.get("data_complete")), data_basis=entry_basis)
                        if (entry["quelle"], entry["id"]) in exclusions:
                            entry.update(eligible=False, hard_excluded=True,
                                         grund="Explizite Ausschlussliste: " + str(exclusions[(entry["quelle"], entry["id"])].get("grund") or "Ausschluss"))
                        if run["dd_grenze"] is not None and _finite(entry.get("equity_dd_pct")) and entry["equity_dd_pct"] > run["dd_grenze"]:
                            entry.update(eligible=False, grund=f"Gewählte Equity-DD-Grenze {run['dd_grenze']:g} % überschritten")
                        entry["status"] = ("datenluecke" if not entry["data_done"] else
                                           "quellenwerte" if entry.get("auswertung_typ") == "quellenprofitabilitaet" else "ki_offen" if _ki_possible(entry)
                                           else "ausgeschlossen" if entry.get("hard_excluded") else "nicht_geeignet")
                    except Exception as exc:
                        if stopped():
                            raise Angehalten("Stop angefordert") from exc
                        entry.update(status="datenluecke", grund=str(exc), eligible=False)
                    store.save_task(run_id, entry)
            if "budget_resume_refs" in run:
                store.update(run_id, budget_resume_refs=[])
        ranked = rank_entries(entries, run["retdd_gewicht"])
        for entry in entries:
            store.save_task(run_id, entry)
        if stopped():
            raise Angehalten("Stop angefordert")
        ai = AnalyseKI(store, run_id, settings, profile, should_stop=stopped, log=log)
        store.update(run_id, phase="kurzanalysen")
        pending_short = False
        for entry in entries:
            if not _ki_possible(entry):
                continue
            basis = kurztest_basis(entry, profile, settings)
            if entry.get("kurz_basis") == basis and entry.get("kurztest"):
                _check_hints(entry, entry["kurztest"].get("pruefhinweise") or [], stage="kurztest")
                store.save_task(run_id, entry)
                continue
            if not ai.client.has_key:
                raise LlmError("Kein GLM-Key konfiguriert; Berechnungen bleiben erhalten. Unter Einstellungen ergänzen und fortsetzen.")
            try:
                _record_hint_origins(entry, entry.get("ki_pruefhinweise") or [])
                entry.update(kurztest=ai.analyse(entry), kurz_basis=basis, ki_fehler="")
                _check_hints(entry, entry["kurztest"].get("pruefhinweise") or [], stage="kurztest")
                entry["status"] = "ausgeschlossen" if entry.get("hard_excluded") else "fertig"
            except (LlmBudgetError, LlmNoBalanceError, Angehalten):
                raise
            except LlmError as exc:
                entry.update(status="ki_fehler", ki_fehler=str(exc))
                pending_short = True
                log(f"Kurztest {entry['name']}: {exc}")
            store.save_task(run_id, entry)
        if pending_short:
            store.update(run_id, status="teilweise", phase="kurzanalysen", detail="Einzelne Kurzanalysen fehlen; fortsetzen möglich")
            return
        store.update(run_id, phase="top5_analysen")
        ranked = rank_entries(entries, run["retdd_gewicht"])
        for entry in entries:
            store.save_task(run_id, entry)
        pending_deep = False
        attempted = set()
        while True:
            ranked = rank_entries(entries, run["retdd_gewicht"])
            comparison = [{k: e.get(k) for k in ("signal_ref", "quelle", "name", "rang", "auswahlwert", "retdd_jahr", "equity_dd_pct", "abo_perzentil", "dauer_monate")}
                          for e in ranked[:5]]
            todo = []
            for candidate in ranked[:5]:
                candidate_basis = digest({"kurz": candidate["kurz_basis"], "comparison": comparison,
                    "prompt": prompts.prompt_fingerprint(("abonnenten_top5",)),
                    "model": prompts.prompt_model("abonnenten_top5", settings)})
                if (candidate["signal_ref"], candidate_basis) not in attempted:
                    todo.append((candidate, candidate_basis))
            if not todo:
                break
            entry, basis = todo[0]
            attempted.add((entry["signal_ref"], basis))
            if stopped():
                raise Angehalten("Stop angefordert")
            try:
                if not entry.get("bericht_markdown") or entry.get("top5_basis") != basis:
                    _record_hint_origins(entry, entry.get("ki_pruefhinweise") or [])
                    answer = ai.analyse(entry, deep=True, comparison=comparison)
                    entry.update(bericht_markdown=answer["bericht_markdown"], top5_befund=answer,
                                 top5_basis=basis, analyse_at=now(),
                                 analyse_model=prompts.prompt_model("abonnenten_top5", settings))
                _check_hints(entry, (entry.get("top5_befund") or {}).get("neue_pruefhinweise") or [], stage="top5")
                entry["status"] = "ausgeschlossen" if entry.get("hard_excluded") else "fertig"
                store.save_task(run_id, entry)  # preserve paid response before PDF work
                entry["pdf_path"] = report_pdf(entry, run_id)
                entry["ki_fehler"] = ""
            except (LlmBudgetError, LlmNoBalanceError, Angehalten):
                raise
            except Exception as exc:
                entry.update(status="ki_fehler", ki_fehler=str(exc))
                pending_deep = True
                log(f"Top 5 {entry['name']}: {exc}")
            store.save_task(run_id, entry)
        ranked = rank_entries(entries, run["retdd_gewicht"])
        for entry in entries:
            store.save_task(run_id, entry)
        source_errors = any(q.get("status") != "fertig"
                            or q.get("abonnenten_katalog", {}).get("complete") is False
                            for q in run.get("snapshot_quellen", {}).values())
        gaps = any(not e.get("data_done") or e.get("review_pending") for e in entries)
        unfinished = pending_deep or any(not e.get("bericht_markdown") for e in ranked[:5])
        final_status = "teilweise" if source_errors or gaps or unfinished else "abgeschlossen"
        reviews = sum(bool(e.get("review_pending")) for e in entries)
        store.update(run_id, status=final_status, phase="ergebnis", finished_at=now(),
                     detail=f"{len(entries)} Anbieter bearbeitet; {len(ranked)} Kandidaten; "
                            f"{sum(bool(e.get('bericht_markdown')) for e in ranked[:5])} ausführliche Top-5-Berichte"
                            + (f"; {reviews} offene KI-Prüfungen" if reviews else ""))
    except Angehalten as exc:
        store.update(run_id, status="angehalten", detail=str(exc))
    except (LlmBudgetError, LlmNoBalanceError) as exc:
        store.update(run_id, status="wartet_budget", detail=str(exc), fehler=str(exc))
    except Exception as exc:
        store.update(run_id, status="teilweise", detail="Lauf unterbrochen; gespeicherte Stufen bleiben erhalten", fehler=str(exc))


def _ki_possible(entry):
    return bool(entry.get("trades_path") and entry.get("forensik") and
                (entry.get("trades") or 0) >= 50 and (entry.get("dauer_monate") or 0) >= 2)


def daten_basis(settings):
    return digest({"version": FORENSICS_VERSION, "policy": POLICY_VERSION,
                   "contracts": config.CONTRACT_SPECS_FILE.read_text(encoding="utf-8") if config.CONTRACT_SPECS_FILE.exists() else "",
                   "kurs_settings": {k: v for k, v in settings.items() if k.startswith(("kursdaten_", "markt_", "equity_"))}})


def eintrag_basis(entry, common, exclusions):
    fields = {"common": common, "exclusion": exclusions.get((entry["quelle"], entry["id"]))}
    if entry["quelle"] == "robo":
        fields["robo_quellenwerte_version"] = 1
    return digest(fields)


def _record_hint_origins(entry, hints, *, stage=None):
    """Retain the original report register; never rebind old F/K/V aliases."""
    if not hints:
        return
    records = entry.setdefault("ki_pruefhinweis_quellen", [])
    for hint in hints:
        if stage is None and any(record["hinweis"] == hint for record in records):
            continue
        found = False
        for kind, field, hint_field, basis_field in (
                ("kurztest", "kurztest", "pruefhinweise", "kurz_basis"),
                ("top5", "top5_befund", "neue_pruefhinweise", "top5_basis")):
            if stage is not None and kind != stage:
                continue
            report = entry.get(field) or {}
            if hint not in (report.get(hint_field) or []):
                continue
            found = True
            record = {"hinweis": deepcopy(hint), "herkunft": {
                "bericht_stufe": kind, "bericht_basis": entry.get(basis_field),
                "data_basis": entry.get("data_basis"), "trades_sha256": entry.get("trades_sha256"),
                "analysegrundlage": deepcopy(report.get("analysegrundlage") or {})}}
            if record not in records:
                records.append(record)
        if not found:
            record = {"hinweis": deepcopy(hint), "herkunft": {
                "status": "Historische Berichtszuordnung unbekannt; keine Bindung an das aktuelle Belegregister."}}
            if record not in records:
                records.append(record)


def _check_hints(entry, hints, *, stage=None):
    """Snapshot integrity is not an adjudication of a new model finding."""
    pending = list(entry.get("ki_pruefhinweise") or [])
    _record_hint_origins(entry, pending)
    _record_hint_origins(entry, hints, stage=stage)
    for hint in hints:
        if hint not in pending:
            pending.append(hint)
    if not pending:
        entry["review_pending"] = False
        return
    db.verify_trade_file(entry["trades_path"], entry["trades_sha256"])
    # The complete code battery already evaluated these same frozen bytes.
    # Only its proven hard facts can change eligibility, not prose/LLM severity.
    findings = entry.get("forensik", {}).get("forensics", {})
    if findings.get("martingale", {}).get("flag") is True:
        entry.update(eligible=False, hard_excluded=True, grund="Martingale-Signatur durch Code belegt.")
    entry["ki_pruefhinweise"] = pending
    entry["review_pending"] = True
    for field in ("rang", "auswahlwert", "retdd_perzentil"):
        entry[field] = None
    entry["ki_hinweisstatus"] = ("Offene KI-Prüfhinweise: Snapshot-Integrität geprüft, Inhalt noch nicht geklärt. "
                                 "Bis zur Klärung keine Kandidatenrangfolge für diesen Anbieter; "
                                 "kein zusätzlicher bestätigter Ausschluss durch die KI.")


def main(argv=None) -> int:
    """Explicit CLI resume, keeping the daemon worker's process alive to completion."""
    import argparse
    import sys
    import time

    # Redirected Windows Python defaults to cp1252. A provider's emoji/CJK
    # name in progress must never terminate this process and its daemon worker.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Bestehenden Abonnenten-Recherchelauf fortsetzen und bis zum Ende warten.")
    parser.add_argument("--resume", required=True, metavar="LAUF_ID", help="ID eines vorhandenen Rechercheauftrags")
    args = parser.parse_args(argv)
    try:
        if not fortsetzen(args.resume):
            print("Der Recherchelauf arbeitet bereits; kein zweiter Worker gestartet.", file=sys.stderr, flush=True)
            return 3
    except Exception as exc:
        print(f"Fortsetzen fehlgeschlagen: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1

    print(f"Recherchelauf {args.resume} gestartet; warte bis zum tatsächlichen Laufende.", flush=True)
    worker = scan_worker.active_run()
    interrupted = False
    if worker is not None:
        if worker.workflow.get("abonnenten_id") != args.resume:
            print("Kein passender Rechercheworker verfügbar; fremden Worker nicht übernommen.", file=sys.stderr, flush=True)
            return 1
        last_message = time.monotonic()
        while worker.thread is not None and worker.thread.is_alive():
            try:
                worker.thread.join(timeout=1)
                if time.monotonic() - last_message >= 10:
                    run = Store().read(args.resume) or {}
                    print(f"{run.get('phase', '')}: {run.get('detail', '')}", flush=True)
                    last_message = time.monotonic()
            except KeyboardInterrupt:
                interrupted = True
                stoppen(args.resume)
                print("Stop angefordert; warte auf sicheren Abschluss und Terminal-Cleanup.", file=sys.stderr, flush=True)
    # A very short worker can already have removed itself from the registry.
    # Its durable terminal status, never registry presence, decides success.
    run = Store().read(args.resume) or {}
    status = run.get("status", "unbekannt")
    print(f"Recherchelauf {args.resume}: {status}; {run.get('detail', '')}", flush=True)
    if interrupted or status == "angehalten":
        return 130
    return 0 if status == "abgeschlossen" else 2


if __name__ == "__main__":
    raise SystemExit(main())
