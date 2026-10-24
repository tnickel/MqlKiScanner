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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Event, Lock

from . import config, db, ingest, quellen as source_registry, scan_worker
from .abonnenten_analyse_store import Store, now
from .abonnenten_analyse_ki import AnalyseKI, Angehalten, FACTS_PAYLOAD_VERSION, digest, report_pdf
from .abonnenten_analyse_parallel import AdaptiveHttpGate
from .analysis_version import FORENSICS_VERSION
from .llm import prompts
from .llm.client import LlmBudgetError, LlmError, LlmNoBalanceError, LlmRateLimitError

POLICY_VERSION = "abonnenten_recherche_v1"
DATA_WORKFLOW_MODE = "daten_ohne_ki_v1"
CAPITAL_MODEL_VERSION = "abonnenten_modellkapital_v1"
BUDGET_SETTING_KEYS = frozenset({
    "llm_max_total_tokens", "agenten_tagesbudget_tokens", "agenten_monatsbudget_tokens",
})
KI_CONFIG_RESTART_FIELD = "ki_config_restart_checkpoint"
_FINISHED_DATA_ATTEMPTS = frozenset({
    "datenluecke", "ki_offen", "ki_fehler", "fertig", "ausgeschlossen", "nicht_geeignet", "quellenwerte",
})
_REDACTION_FIELDS = (
    "bericht_redaktion_verlangt", "bericht_redaktion_basis", "bericht_redaktion_korrekturen",
    "bericht_redaktion_status", "bericht_redaktion_at", "bericht_redaktion_bericht_sha256",
    "bericht_markdown_original", "bericht_redaktion_result", "bericht_redaktion_beleg_register",
)
_FINAL_REVIEW_FIELDS = (
    "ki_pruefentscheidungen", "ki_klaerung_basis", "ki_klaerung_status", "ki_klaerung_gesperrt",
    "ki_klaerung_at", "endpruefung_status", "endpruefung_basis", "endpruefung_pdf_basis",
    "endpruefung_fehler", "endpruefung_at", "top5_comparison", "top5_comparison_basis",
    *_REDACTION_FIELDS,
)


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


def rank_entries(entries: list[dict], weight: float = 70, *, kurztest_optional=False,
                 auswahl_modus=None) -> list[dict]:
    inflow_mode = auswahl_modus == "abo_zufluss_retdd_v1"
    if inflow_mode:
        for entry in entries:
            entry["abo_zufluss_perzentil"] = None
            entry["abo_zufluss_skaliert"] = None
        for source in {entry.get("quelle") for entry in entries}:
            source_entries = [entry for entry in entries if entry.get("quelle") == source]
            observed = [entry["abonnenten"] for entry in source_entries
                        if _finite(entry.get("abonnenten")) and entry["abonnenten"] > 0]
            source_mean = sum(observed) / len(observed) if observed else None
            for entry in entries:
                if entry.get("quelle") == source:
                    # The runner installs the persisted frozen reference first.
                    # Pure ranking callers derive the same reference from all
                    # frozen source entries, never only eligible candidates.
                    mean = entry.get("abo_quellen_durchschnitt", source_mean)
                    entry["abo_quellen_durchschnitt"] = mean
                    entry.setdefault("abo_quellen_referenz_n", len(observed))
                    trend = entry.get("abo_trend") or {}
                    if trend.get("verified") is True and _finite(trend.get("delta_7")) and _finite(mean) and mean > 0:
                        entry["abo_zufluss_skaliert"] = trend["delta_7"] / mean
                    entry["rang_hinweis"] = ("" if entry["abo_zufluss_skaliert"] is not None else
                        "Kein belegtes 7-Tage-Fenster oder kein belegter Quellenmittelwert; keine Rangposition.")
        scaled = percentile({entry["signal_ref"]: entry["abo_zufluss_skaliert"] for entry in entries
                             if entry.get("eligible") and not entry.get("hard_excluded")
                             and not entry.get("ki_klaerung_gesperrt")
                             and _finite(entry.get("retdd_jahr")) and entry["retdd_jahr"] > 0
                             and _finite(entry.get("abo_zufluss_skaliert"))})
        for entry in entries:
            entry["abo_zufluss_perzentil"] = scaled.get(entry["signal_ref"])
    popularity_field = "abo_zufluss_perzentil" if inflow_mode else "abo_perzentil"
    candidates = [e for e in entries if e.get("eligible") and not e.get("hard_excluded") and _finite(e.get("retdd_jahr"))
                  and e["retdd_jahr"] > 0 and _finite(e.get(popularity_field))
                  and (kurztest_optional or not e.get("review_pending"))
                  and not e.get("ki_klaerung_gesperrt")]
    efficiency = percentile({e["signal_ref"]: e["retdd_jahr"] for e in candidates})
    for entry in entries:
        entry["rang"] = entry["auswahlwert"] = entry["retdd_perzentil"] = None
    for entry in candidates:
        entry["retdd_perzentil"] = efficiency[entry["signal_ref"]]
        entry["auswahlwert"] = (weight / 100 * entry["retdd_perzentil"]
                               + (1-weight / 100) * entry[popularity_field])
    def measured_profit(entry):
        value = (entry.get("forensik") or {}).get("stats", {}).get("net")
        return value if _finite(value) else float("-inf")
    if inflow_mode:
        def measured_return(entry):
            # CAGR/return is normalised to capital; raw dollar profit is only
            # a later tie-break, not a preference for a larger source account.
            for value in (entry.get("cagr_jahr_pct"), (entry.get("equity") or {}).get("cagr_jahr_pct"),
                          (entry.get("equity") or {}).get("rendite_pct"),
                          entry.get("rendite_pct")):
                if _finite(value):
                    return value
            return float("-inf")
        candidates.sort(key=lambda e: (-e["auswahlwert"], -measured_return(e), -e["retdd_jahr"], -measured_profit(e),
                                      -(e.get("dauer_monate") or 0), str(e.get("quellen_uid") or e["quelle"]), e["id"]))
    else:
        candidates.sort(key=lambda e: (-e["auswahlwert"], -e["retdd_jahr"], -(e.get("dauer_monate") or 0),
                                      str(e.get("quellen_uid") or e["quelle"]), e["id"]))
    for index, entry in enumerate(candidates, 1):
        entry["rang"] = index
    return candidates


def rank_datamodus(entries: list[dict], weight: float = 30) -> list[dict]:
    """Rank one explicitly labelled basis; never write model values over facts."""
    copies = deepcopy(entries)
    model_mode = any(isinstance(entry.get("modell"), dict) for entry in copies)
    for entry in copies:
        entry["ki_klaerung_gesperrt"] = False
        entry["review_pending"] = False
        if model_mode:
            model = entry.get("modell") or {}
            for field in ("retdd_jahr", "equity_dd_pct", "cagr_jahr_pct", "rendite_zeitraum_pct"):
                entry[field] = model.get(field)
            entry["forensik"] = {"stats": {"net": model.get("nettogewinn_usd")}}
            entry["eligible"] = (model.get("status") == "berechnet"
                                 and entry.get("trade_history_complete") is True
                                 and _finite(model.get("equity_dd_pct"))
                                 and model["equity_dd_pct"] > 0
                                 and _finite(model.get("retdd_jahr")))
        elif entry.get("data_done") is False:
            entry["eligible"] = False
    rank_entries(copies, weight, kurztest_optional=True, auswahl_modus="abo_zufluss_retdd_v1")
    derived = ("rang", "auswahlwert", "retdd_perzentil", "abo_zufluss_perzentil", "abo_zufluss_skaliert",
               "abo_quellen_durchschnitt", "abo_quellen_referenz_n", "rang_hinweis")
    by_ref = {entry["signal_ref"]: entry for entry in copies}
    for entry in entries:
        entry.update({key: by_ref[entry["signal_ref"]].get(key) for key in derived})
    return sorted((entry for entry in entries if entry.get("rang") is not None), key=lambda entry: entry["rang"])


def _profile(run: dict) -> dict:
    result = {"policy_version": POLICY_VERSION, "min_monate": 2, "min_trades": 50,
            "retdd_definition": "Jahres-CAGR / maximaler gemessener relativer Equity-DD inklusive Floating",
            "dd_grenze": run["dd_grenze"], "retdd_gewicht": run["retdd_gewicht"],
            "abonnenten_gewicht": 100-run["retdd_gewicht"], "top_n_je_quelle": 200,
            "min_abonnenten": 1, "messbasis": "Historisches Exportfenster; H1-Schlüsse, keine Intrabar-Tiefs; aktueller offener Bestand nicht belegt"}
    if run.get("kurztest_optional"):
        result.update(kurztest_optional=True, endpruefung_auto=bool(run.get("endpruefung_auto")))
    if run.get("auswahl_modus"):
        result["auswahl_modus"] = run["auswahl_modus"]
    if run.get("auswahl_modus") == "abo_zufluss_retdd_v1":
        result["abonnenten_messgroesse"] = (
            "Globales Perzentil der nativen Netto-Bestandsänderung über 7 Tage ±3 Tage geteilt durch "
            "den durchschnittlichen positiven Abonnentenbestand der eingefrorenen Auswahl derselben Quelle; "
            "keine Bruttozuwanderung. Fehlende belegte Fenster bleiben unbekannt und ohne Rang.")
        if run.get("abo_quellen_referenz"):
            result["abo_quellen_referenz"] = run["abo_quellen_referenz"]
    return result


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
    if run.get("workflow_modus") == DATA_WORKFLOW_MODE:
        rank_datamodus(entries, run["retdd_gewicht"])
    elif run.get("auswahl_modus") == "abo_zufluss_retdd_v1":
        # A live worker persists each finalist independently. Derive one
        # coherent current view from the loaded frozen inputs; never write
        # display-only ranks back into its concurrently owned tasks.
        rank_entries(entries, run["retdd_gewicht"],
                     kurztest_optional=bool(run.get("kurztest_optional")),
                     auswahl_modus=run["auswahl_modus"])
    run["entries"] = sorted(entries, key=lambda e: (e.get("rang") or 10**9, e.get("quelle", ""), e.get("name", "")))
    run["laeuft"] = _alive(run)
    if run["status"] == "laeuft" and not run["laeuft"]:
        run["status"] = "unterbrochen"
        run["detail"] = "Workerprozess beendet; gespeicherte Stufen können fortgesetzt werden."
    run["total"] = len(entries)
    run["done"] = sum(e.get("status") in {"fertig", "ausgeschlossen", "datenluecke", "nicht_geeignet", "quellenwerte"} for e in entries)
    run["tokens"] = 0 if run.get("workflow_modus") == DATA_WORKFLOW_MODE else store.spent(run["id"])
    return run


def laeufe() -> list[dict]:
    return [{k: row.get(k) for k in ("id", "status", "created_at", "quellen", "retdd_gewicht", "dd_grenze",
                                    "workflow_modus", "daten_status", "abgeleitet_von")}
            for row in Store().runs()]


def starten(quellen: list[str], settings=None, retdd_gewicht=70, dd_grenze=None, *,
            auswahl_modus=None, kurztest_optional=False, endpruefung_auto=False) -> str:
    if not _finite(retdd_gewicht) or not 0 <= retdd_gewicht <= 100:
        raise ValueError("RetDD-Gewicht muss zwischen 0 und 100 liegen")
    if dd_grenze is not None and (not _finite(dd_grenze) or dd_grenze <= 0):
        raise ValueError("Die optionale DD-Grenze muss positiv sein")
    if auswahl_modus not in {None, "abo_bestand_retdd_v1", "abo_zufluss_retdd_v1"}:
        raise ValueError("Unbekannter Auswahlmodus")
    if type(kurztest_optional) is not bool or type(endpruefung_auto) is not bool:
        raise ValueError("Optionen für Kurztest und Endprüfung müssen boolesch sein")
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
    if auswahl_modus is not None:
        run["auswahl_modus"] = auswahl_modus
    if kurztest_optional:
        run["kurztest_optional"] = True
    if endpruefung_auto:
        run["endpruefung_auto"] = True
    run["ki_parallelitaet"] = _ki_parallelitaet(
        run, {**config.load_settings(), **(settings or {})}, new_run=True)
    store = Store()
    store.create(run)
    try:
        _launch(run_id, settings)
    except Exception as exc:
        store.update(run_id, status="fehlgeschlagen", fehler=str(exc))
        raise
    return run_id


def _data_run(quellen, retdd_gewicht, dd_grenze):
    if not _finite(retdd_gewicht) or not 0 <= retdd_gewicht <= 100:
        raise ValueError("RetDD-Gewicht muss zwischen 0 und 100 liegen")
    if dd_grenze is not None and (not _finite(dd_grenze) or dd_grenze <= 0):
        raise ValueError("Die optionale DD-Grenze muss positiv sein")
    return {"id": uuid.uuid4().hex, "created_at": now(), "updated_at": now(), "status": "geplant",
            "phase": "geplant", "workflow_modus": DATA_WORKFLOW_MODE, "policy_version": POLICY_VERSION,
            "quellen": list(quellen), "retdd_gewicht": float(retdd_gewicht), "dd_grenze": dd_grenze,
            "auswahl_modus": "abo_zufluss_retdd_v1", "snapshot_quellen": {}, "logs": [],
            "stop_requested": False, "fehler": "", "detail": "Datenbeschaffung und Kennzahlen ohne KI vorbereitet",
            "daten_status": "geplant", "daten_workflow_abgeschlossen": False, "daten_vollstaendig": False}


def daten_starten(quellen: list[str], settings=None, retdd_gewicht=30, dd_grenze=None) -> str:
    """Explicitly start a separate data-only job without KI prerequisites."""
    active = db.list_quellen(nur_aktiv=True)
    chosen = {db.kanonische_quelle(source) for source in quellen}
    if not chosen or chosen - {db.kanonische_quelle(source["kuerzel"]) for source in active}:
        raise ValueError("Mindestens eine gültige aktive Quelle auswählen")
    run = _data_run(sorted(chosen), retdd_gewicht, dd_grenze)
    run.update(kapitalmodell_aktiv=True, modell_version=CAPITAL_MODEL_VERSION)
    store = Store()
    store.create(run)
    try:
        _launch(run["id"], settings)
    except Exception as exc:
        store.update(run["id"], status="fehlgeschlagen", daten_status="fehler", fehler=str(exc))
        raise
    return run["id"]


def daten_fortsetzen(run_id: str) -> bool:
    run = Store().read(run_id)
    if not run or run.get("workflow_modus") != DATA_WORKFLOW_MODE:
        raise ValueError("Nur ein ausdrücklich angelegter Datenauftrag kann ohne KI fortgesetzt werden")
    if _alive(run):
        return False
    _launch(run_id)
    return True


def modell_aus_lauf(run_id: str, *, starten=True) -> str:
    """Explicit model calculation from a preserved copy, using local data only."""
    if type(starten) is not bool:
        raise ValueError("starten muss boolesch sein")
    original = Store().read(run_id)
    if not original:
        raise ValueError("Unbekannter ursprünglicher Auftrag")
    if _alive(original):
        raise ValueError("Der ursprüngliche Auftrag arbeitet noch; stabilen Datenstand abwarten.")
    new_id = daten_aus_lauf(run_id)
    store = Store()
    # A fresh model uses current verified inputs and a newly frozen calibration.
    # Historical scenarios remain in their owning job, never silently replaced.
    for entry in store.tasks(new_id):
        entry.pop("modell", None)
        store.save_task(new_id, entry)
    store.update(new_id, kapitalmodell_aktiv=True, modell_nur_bestand=True,
                 modell_version=CAPITAL_MODEL_VERSION, phase="kapitalmodell",
                 status="geplant", daten_status="geplant", modell_abgeschlossen=False,
                 daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False,
                 detail="Kapitalmodell aus gespeicherten Trades und Kursen vorbereitet; Annahme keine Ein-/Auszahlungen.")
    if starten:
        try:
            _launch(new_id)
        except Exception as exc:
            store.update(new_id, status="fehlgeschlagen", daten_status="fehler", fehler=str(exc))
            raise
    return new_id


def daten_aus_lauf(run_id: str, settings=None, *, fortsetzen=False) -> str:
    """Copy verified measurements into a NEW job; never alter the original KI job.

    By default this performs no download or terminal work. Missing/obsolete
    evidence remains a visible data gap until the new job is explicitly resumed.
    """
    if type(fortsetzen) is not bool:
        raise ValueError("fortsetzen muss boolesch sein")
    store = Store()
    original = store.read(run_id)
    if not original:
        raise ValueError("Unbekannter ursprünglicher Auftrag")
    settings = {**config.load_settings(), **(settings or {})}
    run = _data_run(original["quellen"], 30, original.get("dd_grenze"))
    run.update(abgeleitet_von=run_id, abgeleitet_am=now(), snapshot_quellen=deepcopy(original.get("snapshot_quellen") or {}),
               detail="Vorhandene Daten kopiert; Quellensnapshot und Messzeiten unverändert, keine neue Beschaffung")
    original_entries = store.tasks(run_id)
    run["uebernahme_basis"] = digest({"run": original, "entries": original_entries})
    if original.get("abo_quellen_referenz"):
        run["abo_quellen_referenz"] = deepcopy(original["abo_quellen_referenz"])
    common, exclusions = daten_basis(settings), _restart_exclusions()
    entries = []
    ki_fields = {"kurztest", "kurz_basis", "bericht_markdown", "top5_basis", "top5_befund", "pdf_path",
                 "review_pending", "ki_pruefhinweise", "ki_pruefhinweis_quellen", "ki_hinweisstatus",
                 "ki_fehler", "previous_results", "analyse_at", "analyse_model", *_FINAL_REVIEW_FIELDS}
    for original_entry in original_entries:
        entry = {key: deepcopy(value) for key, value in original_entry.items() if key not in ki_fields}
        _derive_legacy_export_receipt(entry, original_run_id=run_id)
        reusable = _data_attempt_reusable(entry, common, exclusions)
        entry.update(data_done=reusable, daten_uebernahme={"lauf_id": run_id,
                     "signal_ref": entry["signal_ref"], "daten_basis": original_entry.get("data_basis"),
                     "urspruenglicher_status": original_entry.get("status"), "belege_geprueft": reusable},
                     status=("quellenwerte" if reusable and entry.get("auswertung_typ") == "quellenprofitabilitaet"
                             else "ausgeschlossen" if reusable and entry.get("hard_excluded")
                             else "fertig" if reusable else "datenluecke"))
        if not reusable:
            entry["daten_uebernahme_hinweis"] = (
                "Übernommener Datenstand nicht vollständig oder nicht auf aktueller Basis/Snapshot belegt; Datenfortsetzung erforderlich.")
            if not entry.get("grund"):
                entry["grund"] = entry["daten_uebernahme_hinweis"]
        entries.append(entry)
    store.create(run)
    for entry in entries:
        store.save_task(run["id"], entry)
    _freeze_source_means(store, run["id"], run, entries)
    _finish_data_job(store, run, entries, imported=True)
    if fortsetzen:
        _launch(run["id"], settings)
    return run["id"]


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


def _ki_parallelitaet(run: dict, settings: dict, *, new_run=False) -> int:
    # An old saved run must not silently inherit a newly raised global default.
    value = run.get("ki_parallelitaet", settings.get("abonnenten_analyse_parallelitaet", 1) if new_run else 1)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
        raise ValueError("KI-Parallelität muss eine ganze Zahl zwischen 1 und 10 sein")
    return value


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
                   **({"auswahl_luecken": entry.get("abo_ausgelassene_positionen"),
                       **({"auswahl_hinweis": entry["abo_auswahl_hinweis"]}
                          if entry.get("abo_auswahl_hinweis") else {})}
                      if entry.get("abo_referenz_vollstaendig") is False else {}),
                   "prompt": prompts.prompt_fingerprint(("abonnenten_kurztest",)),
                   "model": prompts.prompt_model("abonnenten_kurztest", settings)})


def _launch(run_id, settings=None):
    store = Store()
    run = store.read(run_id)
    if not run:
        raise ValueError("Unbekannter Bewertungslauf")
    if run.get("workflow_modus") == DATA_WORKFLOW_MODE:
        settings = {**config.load_settings(), **(settings or {})}
    else:
        overrides = _budget_settings(run)  # validate before creating any KI worker
        settings = {**config.load_settings(), **(settings or {}), **overrides}
        _ki_parallelitaet(run, settings)
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
                           and ((coverage.get("complete") is False
                                 and coverage.get("reached_end") is True
                                 and bool(coverage.get("skipped_positions")))
                                or update.get("abonnenten_auswahl_unbestaetigt") is True)
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
            raw = ingest.hole_katalog(source, client=cli, min_subscribers=1, catalog_scope="subscribers")
            if ingest.katalog_scope(raw) == "full":
                raise ValueError("Quelle liefert Vollkatalog statt angeforderter frischer Abonnentenauswahl")
            selection_unverified = (not coverage and not update.get("abonnenten_auswahl", {}).get("verified"))
            selection_warning = ("Abonnentenauswahl/Abdeckung unbestätigt: kein Auswahl- oder Katalogbeleg; "
                                 "globale Top 200 nicht bestätigt." if selection_unverified else "")
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
                elif selection_unverified:
                    entry.update(abo_referenz_vollstaendig=False, abo_ausgelassene_positionen=[],
                                 abo_katalog_geprueft=None, abo_auswahl_hinweis=selection_warning)
                else:
                    entry["abo_referenz_vollstaendig"] = True
                if health.get("providerRefresh") is not True:
                    entry["quellen_hinweis"] = health.get("providerRefreshReason") or "Gezielter Anbieterabruf benötigt einen aktualisierten Client"
            checkpoint = {"status": "fertig", "anzahl": len(valid), "stand": now(), "update_job": update.get("job_id")}
            if coverage:
                checkpoint["abonnenten_katalog"] = coverage
            if update.get("abonnenten_auswahl"):
                checkpoint["abonnenten_auswahl"] = update["abonnenten_auswahl"]
            if selection_unverified:
                checkpoint.update(abonnenten_auswahl_unbestaetigt=True, auswahl_hinweis=selection_warning)
            done = store.freeze_source(run["id"], name, valid, checkpoint)
            log(f"{name}: {len(valid)} Anbieter im Prüfauftrag festgeschrieben")
            if coverage.get("complete") is False:
                log(f"{name}: Auswahl aus lesbaren Anbietern; "
                    f"{len(coverage['skipped_positions'])} API-Position(en) ausgelassen.")
            if selection_warning:
                log(f"{name}: {selection_warning}")
        except Exception as exc:
            done[name] = {"status": "fehler", "grund": str(exc)}
            log(f"Quelle {name}: {exc}")
        store.update(run["id"], snapshot_quellen=done)


class _KeinKiSchluessel(LlmError):
    """Missing credentials stop dispatch, rather than failing every strategy."""


def _kurzanalysen(store, run_id, entries, settings, profile, stopped, log, slots):
    """Bounded strategy tasks; only this coordinator mutates saved entries.

    Every task owns its AnalyseKI/client and evidence/cost state. On any
    interruption all submitted tasks are drained before returning or raising;
    completed paid reports are still merged while the run lock remains held.
    """
    halt, failure_lock = Event(), Lock()
    failures = []
    pending_short = False
    iterator = iter(entries)
    exhausted = False
    active = {}

    def fail(exc):
        with failure_lock:
            failures.append(exc)
            halt.set()

    def task_stopped():
        return halt.is_set() or stopped()

    def check_stop():
        if task_stopped():
            raise Angehalten("Stop angefordert")

    def http_progress(snapshot):
        store.update(run_id, ki_http_limit=snapshot["limit"], ki_http_aktiv=snapshot["active"],
                     ki_http_max_aktiv=snapshot["max_active"], ki_drosselungen=snapshot["throttles"])

    gate = AdaptiveHttpGate(max_limit=slots, check_stop=check_stop, log=log, on_change=http_progress)
    http_progress(gate.status())

    def task(entry):
        try:
            if task_stopped():
                raise Angehalten("Stop angefordert")
            ai = AnalyseKI(store, run_id, deepcopy(settings), deepcopy(profile),
                           should_stop=task_stopped,
                           log=lambda message: log(f"{entry['quelle']}:{entry['id']} · {message}"))
            ai.client.request_gate = gate
            if not ai.client.has_key:
                raise _KeinKiSchluessel("Kein GLM-Key konfiguriert; Berechnungen bleiben erhalten. "
                                       "Unter Einstellungen ergänzen und fortsetzen.")
            return ai.analyse(deepcopy(entry))
        except BaseException as exc:
            if not isinstance(exc, LlmError) or isinstance(exc, (
                    Angehalten, LlmBudgetError, LlmNoBalanceError, LlmRateLimitError, _KeinKiSchluessel)):
                fail(exc)
            raise

    def progress():
        try:
            store.update(run_id, ki_aktive_slots=len(active))
        except BaseException as exc:
            fail(exc)

    progress()
    with ThreadPoolExecutor(max_workers=slots, thread_name_prefix="abonnenten-kurztest") as executor:
        while active or (not exhausted and not halt.is_set()):
            try:
                if stopped() and not halt.is_set():
                    fail(Angehalten("Stop angefordert"))
                while not exhausted and not halt.is_set() and len(active) < slots:
                    entry = next(iterator, None)
                    if entry is None:
                        exhausted = True
                        break
                    if not _ki_possible(entry):
                        continue
                    basis = kurztest_basis(entry, profile, settings)
                    if entry.get("kurz_basis") == basis and entry.get("kurztest"):
                        _check_hints(entry, entry["kurztest"].get("pruefhinweise") or [], stage="kurztest")
                        store.save_task(run_id, entry)
                        continue
                    if stopped():
                        fail(Angehalten("Stop angefordert"))
                        break
                    # Fatal task failures and submission share this lock so a
                    # known failure never leaves another queued strategy.
                    with failure_lock:
                        if halt.is_set():
                            break
                        future = executor.submit(task, entry)
                        active[future] = (entry, basis)
                    progress()
            except BaseException as exc:
                fail(exc)
            if not active:
                break
            completed, _ = wait(active, timeout=.2, return_when=FIRST_COMPLETED)
            for future in completed:
                entry, basis = active.pop(future)
                try:
                    answer = future.result()
                except BaseException as exc:
                    if isinstance(exc, LlmError) and not isinstance(exc, (
                            Angehalten, LlmBudgetError, LlmNoBalanceError, LlmRateLimitError, _KeinKiSchluessel)):
                        entry.update(status="ki_fehler", ki_fehler=str(exc))
                        pending_short = True
                        try:
                            log(f"Kurztest {entry['name']}: {exc}")
                            store.save_task(run_id, entry)
                        except BaseException as save_exc:
                            fail(save_exc)
                    # Fatal errors are recorded by the task before its future
                    # completes. Peers may only report a cooperative stop.
                    continue
                try:
                    _record_hint_origins(entry, entry.get("ki_pruefhinweise") or [])
                    entry.update(kurztest=answer, kurz_basis=basis, ki_fehler="")
                    # Preserve the completed paid result even if a later
                    # snapshot/hint integrity check raises an interruption.
                    store.save_task(run_id, entry)
                    _check_hints(entry, answer.get("pruefhinweise") or [], stage="kurztest")
                    entry["status"] = "ausgeschlossen" if entry.get("hard_excluded") else "fertig"
                    store.save_task(run_id, entry)
                except BaseException as exc:
                    fail(exc)
            progress()
    # All worker callbacks have ended; publish an authoritative final snapshot
    # after concurrent display updates so no older active count can remain.
    http_progress(gate.status())
    # The executor has joined every submitted task. Do not label a peer's
    # induced stop as the cause when a real budget/provider failure triggered it.
    if failures:
        raise next((exc for exc in failures if not isinstance(exc, Angehalten)), failures[0])
    if stopped():
        raise Angehalten("Stop angefordert")
    return pending_short


def _current_short(entry, profile, settings):
    """An optional stale add-on is never evidence for a new final report."""
    if entry.get("kurztest") and entry.get("kurz_basis") == kurztest_basis(entry, profile, settings):
        return entry["kurztest"]
    return None


def top5_basis(entry, profile, settings, comparison):
    short = _current_short(entry, profile, settings)
    return digest({"version": 3, "data": entry.get("data_basis"), "sha": entry.get("trades_sha256"),
                   "facts_payload_version": FACTS_PAYLOAD_VERSION, "facts": entry.get("forensik"),
                   "equity": entry.get("equity"), "profile": profile, "trend": entry.get("abo_trend"),
                   "output_contract": {"max_tokens": 32_768 if profile.get("endpruefung_auto") else 16_384,
                                       "reasoning_effort": "high"},
                   "short": short, "short_basis": entry.get("kurz_basis") if short else None,
                   "comparison": comparison, "prompt": prompts.prompt_fingerprint(("abonnenten_top5",)),
                   "model": prompts.prompt_model("abonnenten_top5", settings)})


def _final_pdf_basis(entry, basis):
    from . import abonnenten_analyse_ki
    return digest({"top5_basis": basis, "report": entry.get("bericht_markdown"),
                   "appendix_version": getattr(abonnenten_analyse_ki, "REPORT_APPENDIX_VERSION", 1),
                   "trend": entry.get("abo_trend"), "source_mean": entry.get("abo_quellen_durchschnitt"),
                   "source_reference_n": entry.get("abo_quellen_referenz_n"),
                   "source_scope": entry.get("abo_quellen_referenz_scope"),
                   "scaled_inflow": entry.get("abo_zufluss_skaliert"),
                   "resolution_basis": entry.get("ki_klaerung_basis"),
                   "decisions": entry.get("ki_pruefentscheidungen"),
                   "resolution_status": entry.get("ki_klaerung_status"),
                   "blocked": entry.get("ki_klaerung_gesperrt"),
                   "redaction_required": entry.get("bericht_redaktion_verlangt"),
                   "redaction_basis": entry.get("bericht_redaktion_basis"),
                   "redaction_status": entry.get("bericht_redaktion_status"),
                   "redaction_corrections": entry.get("bericht_redaktion_korrekturen"),
                   "redaction_report_sha256": entry.get("bericht_redaktion_bericht_sha256"),
                   "redaction_result": entry.get("bericht_redaktion_result"),
                   "redaction_evidence_register": entry.get("bericht_redaktion_beleg_register")})


def _final_report_complete(entry, basis):
    from pathlib import Path
    from .abonnenten_analyse_klaerung import has_current_resolution
    if (entry.get("endpruefung_status") != "abgeschlossen" or entry.get("endpruefung_basis") != basis
            or entry.get("top5_basis") != basis or not entry.get("bericht_markdown")
            or entry.get("ki_klaerung_gesperrt")
            or (entry.get("ki_pruefhinweise") and not has_current_resolution(entry))
            or entry.get("endpruefung_pdf_basis") != _final_pdf_basis(entry, basis)):
        return False
    if entry.get("bericht_redaktion_verlangt"):
        from .abonnenten_analyse_redaktion import has_current_review
        if entry.get("bericht_redaktion_status") != "geprueft" or not has_current_review(entry):
            return False
    try:
        with Path(entry["pdf_path"]).open("rb") as document:
            return document.read(5) == b"%PDF-"
    except (OSError, KeyError, TypeError):
        return False


def _optional_comparison(ranked):
    fields = ("signal_ref", "quelle", "name", "rang", "auswahlwert", "retdd_jahr", "equity_dd_pct",
              "abo_perzentil", "abo_zufluss_perzentil", "abo_zufluss_skaliert",
              "abo_quellen_durchschnitt", "abo_quellen_referenz_n", "dauer_monate", "cagr_jahr_pct")
    return [{**{key: entry.get(key) for key in fields},
             "abo_delta_7": (entry.get("abo_trend") or {}).get("delta_7"),
             "profit_usd": (entry.get("forensik") or {}).get("stats", {}).get("net")}
            for entry in ranked[:5]]


def reconstruct_top5_comparison(entry, entries, run, settings, *, block_masks=()):
    """Recover original comparison only through the paid report's exact hash.

    ``block_masks`` are explicitly supplied historical sets of blocked signal
    references, such as a preflight mask followed by its audited terminal
    decisions. This helper does not infer history or modify caller entries.
    Multiple masks producing the same verified comparison are harmless;
    an unmatched comparison is never rebound to existing V-register aliases.
    """
    recorded_basis = entry.get("top5_basis")
    if not isinstance(recorded_basis, str) or not recorded_basis:
        raise ValueError("Originalvergleich ohne gespeicherte Top-5-Berichtsbasis nicht belegbar")
    profile = _profile(run)
    saved = entry.get("top5_comparison")
    if isinstance(saved, list) and top5_basis(entry, profile, settings, saved) == recorded_basis:
        return deepcopy(saved)
    refs = {row["signal_ref"] for row in entries}
    candidates = {}
    for mask in block_masks:
        if (not isinstance(mask, (set, frozenset, list, tuple))
                or any(type(ref) is not int or ref not in refs for ref in mask)):
            raise ValueError("Originalvergleich: historische Sperrmaske ungültig oder fremd")
        masked = deepcopy(entries)
        blocked = set(mask)
        for row in masked:
            row["ki_klaerung_gesperrt"] = row["signal_ref"] in blocked
        ranked = rank_entries(masked, run["retdd_gewicht"], kurztest_optional=True,
                              auswahl_modus=run.get("auswahl_modus"))
        if entry["signal_ref"] not in {row["signal_ref"] for row in ranked[:5]}:
            continue
        comparison = _optional_comparison(ranked)
        if top5_basis(entry, profile, settings, comparison) == recorded_basis:
            candidates[digest(comparison)] = comparison
    if len(candidates) != 1:
        raise ValueError("Originalvergleich konnte nicht eindeutig gegen den gespeicherten Top-5-Hash belegt werden")
    return deepcopy(next(iter(candidates.values())))


def _reset_report_redaction(entry):
    """A new raw deep report cannot inherit an earlier editorial clearance."""
    if any(key in entry for key in _REDACTION_FIELDS):
        entry.setdefault("bericht_redaktion_history", []).append({
            "top5_basis": entry.get("top5_basis"),
            "top5_comparison": deepcopy(entry.get("top5_comparison")),
            **{key: deepcopy(entry[key]) for key in _REDACTION_FIELDS if key in entry}})
    for key in _REDACTION_FIELDS:
        entry.pop(key, None)


def _clear_final_error(entry):
    """A completed answer/decision is not an ongoing old transport failure."""
    entry["ki_fehler"] = ""
    entry["endpruefung_fehler"] = ""
    if entry.get("status") == "ki_fehler":
        entry["status"] = "ausgeschlossen" if entry.get("hard_excluded") else "fertig"


def _sync_final_blocks(entry, *, redaction=None):
    """Only a current negative decision can supply the final-review block.

    A valid positive clarification does not preserve a stale editorial veto.
    Conversely, a saved false flag cannot override a current negative verdict.
    Clearing an outdated veto only schedules another final check; it never
    grants final completion or changes the underlying code eligibility.
    """
    from .abonnenten_analyse_klaerung import has_current_resolution
    clarification_block = has_current_resolution(entry) and any(
        decision.get("auswirkung") == "bewertungsgrundlage_unzureichend"
        for decision in entry.get("ki_pruefentscheidungen") or [] if isinstance(decision, dict))
    editorial_block = (redaction is not None and entry.get("bericht_redaktion_status") == "unbeurteilbar"
                       and redaction.has_current_review(entry, allow_blocked=True))
    previous = bool(entry.get("ki_klaerung_gesperrt"))
    current = bool(clarification_block or editorial_block)
    entry["ki_klaerung_gesperrt"] = current
    if current:
        for field in ("rang", "auswahlwert", "retdd_perzentil"):
            entry[field] = None
    elif previous:
        entry["endpruefung_status"] = "wartet"
    return current


def _freeze_source_means(store, run_id, run, entries):
    references = deepcopy(run.get("abo_quellen_referenz") or {})
    for source in run["quellen"]:
        members = sorted(({"signal_ref": entry["signal_ref"], "abonnenten": entry.get("abonnenten")}
                          for entry in entries if entry.get("quelle") == source), key=lambda row: row["signal_ref"])
        membership = digest(members)
        if source in references:
            if references[source].get("auswahl_basis") != membership:
                raise ValueError(f"Eingefrorene Abonnentenreferenz für {source} passt nicht mehr zur ursprünglichen Auswahl")
        else:
            observed = [row["abonnenten"] for row in members
                        if _finite(row["abonnenten"]) and row["abonnenten"] > 0]
            references[source] = {"durchschnitt": sum(observed) / len(observed) if observed else None,
                                  "bekannte_positive_n": len(observed), "auswahl_n": len(members),
                                  "auswahl_basis": membership,
                                  "scope": "Eingefrorene ursprüngliche Top-200-Auswahl positiver Anbieter dieser Quelle; kein Plattformvollmittel",
                                  "quellen_stand": (run.get("snapshot_quellen") or {}).get(source, {}).get("stand"),
                                  "frozen_at": now()}
    for entry in entries:
        reference = references.get(entry.get("quelle")) or {}
        entry.update(abo_quellen_durchschnitt=reference.get("durchschnitt"),
                     abo_quellen_referenz_n=reference.get("bekannte_positive_n", 0),
                     abo_quellen_referenz_scope=reference.get("scope"))
    run["abo_quellen_referenz"] = references
    store.update(run_id, abo_quellen_referenz=references)


def _execute_optional_finalists(store, run_id, run, entries, settings, profile, log, stopped):
    """Rank measured inflow first; spend final-review work only on finalists."""
    from .abonnenten_analyse_klaerung import KlaerungKI, apply_resolution, has_current_resolution
    redaction = None
    if run.get("endpruefung_auto"):
        from . import abonnenten_analyse_redaktion as redaction
    if run.get("auswahl_modus") == "abo_zufluss_retdd_v1":
        _freeze_source_means(store, run_id, run, entries)
        profile.update(_profile(run))
        from .abonnenten_analyse_trend import freeze_trends
        store.update(run_id, phase="abonnenten_trends")
        freeze_trends(store, run_id, entries, settings, log, stopped)
    for entry in entries:
        if redaction is not None and entry.get("eligible"):
            entry["bericht_redaktion_verlangt"] = True
        current_short = _current_short(entry, profile, settings)
        if current_short:
            _check_hints(entry, current_short.get("pruefhinweise") or [], stage="kurztest")
        _sync_final_blocks(entry, redaction=redaction)
        store.save_task(run_id, entry)
    rank = lambda: rank_entries(entries, run["retdd_gewicht"], kurztest_optional=True,
                               auswahl_modus=run.get("auswahl_modus"))
    store.update(run_id, phase="top5_analysen")
    ai = AnalyseKI(store, run_id, settings, profile, should_stop=stopped, log=log)
    # High-reasoning final reports may take longer than the normal add-on KI.
    # Keep this local to the explicitly chosen final workflow, including
    # clients supplied by tests without a pre-existing timeout attribute.
    configured_timeout = getattr(ai.client, "timeout", None)
    ai.client.timeout = max(900, configured_timeout if _finite(configured_timeout) else 0)
    def check_final_stop():
        if stopped():
            raise Angehalten("Stop angefordert")
    final_gate = AdaptiveHttpGate(max_limit=1, check_stop=check_final_stop, log=log)
    ai.client.request_gate = final_gate
    reviewer = None
    editor = None
    attempted = set()

    def clarify(entry):
        nonlocal reviewer
        if not entry.get("ki_pruefhinweise") or has_current_resolution(entry):
            return
        if not run.get("endpruefung_auto"):
            raise LlmError("Offene Endprüfhinweise benötigen eine ausdrücklich aktivierte inhaltliche Klärung")
        if reviewer is None:
            reviewer = KlaerungKI(store, run_id, settings, profile, should_stop=stopped, log=log)
            reviewer.client.request_gate = final_gate
        if not reviewer.client.has_key:
            raise _KeinKiSchluessel("Kein GLM-Key für die inhaltliche Endprüfung konfiguriert")
        log(f"Inhaltliche Endprüfung: {entry['quelle']} · {entry['name']}")
        answer = reviewer.klaeren(entry)
        apply_resolution(entry, answer, trade_refs=answer.get("gelieferte_trade_refs", []))
        _clear_final_error(entry)
        store.save_task(run_id, entry)

    def review_report(entry):
        nonlocal editor
        if redaction is None:
            return
        entry["bericht_redaktion_verlangt"] = True
        if redaction.has_current_review(entry):
            _clear_final_error(entry)
            return
        if editor is None:
            editor = redaction.BerichtRedaktionKI(store, run_id, settings, profile,
                                                  should_stop=stopped, log=log)
            editor.client.request_gate = final_gate
        if not editor.client.has_key:
            raise _KeinKiSchluessel("Kein GLM-Key für die inhaltliche Berichtsredaktion konfiguriert")
        log(f"Berichtsredaktion: {entry['quelle']} · {entry['name']}")
        answer = editor.pruefen(entry)
        redaction.apply_review(entry, answer)
        _clear_final_error(entry)
        store.save_task(run_id, entry)

    while True:
        if stopped():
            raise Angehalten("Stop angefordert")
        ranked = rank()
        comparison = _optional_comparison(ranked)
        todo = []
        for candidate in ranked[:5]:
            basis = top5_basis(candidate, profile, settings, comparison)
            if not _final_report_complete(candidate, basis) and (candidate["signal_ref"], basis) not in attempted:
                todo.append((candidate, basis))
        if not todo:
            break
        entry, basis = todo[0]
        attempted.add((entry["signal_ref"], basis))
        entry.update(endpruefung_status="laeuft", endpruefung_fehler="")
        if entry.get("bericht_markdown") and entry.get("top5_basis") == basis:
            if not entry.get("top5_comparison"):
                # Matching the freshly recomputed v3 hash proves this context
                # before any old V-referenced question is clarified again.
                entry.update(top5_comparison=deepcopy(comparison), top5_comparison_basis=basis)
            _record_hint_origins(entry, (entry.get("top5_befund") or {}).get("neue_pruefhinweise") or [],
                                 stage="top5")
        store.save_task(run_id, entry)
        try:
            # Old short hints are optional for screening but concrete finalist
            # questions are substantively adjudicated before the final report.
            _check_hints(entry, [], stage="kurztest")
            clarify(entry)
            if entry.get("ki_klaerung_gesperrt") or entry.get("hard_excluded"):
                _clear_final_error(entry)
                entry["endpruefung_status"] = "nicht_beurteilbar"
                store.save_task(run_id, entry)
                continue
            rank()  # hint checking removes derived ranks until decisions exist
            if not entry.get("bericht_markdown") or entry.get("top5_basis") != basis:
                if not ai.client.has_key:
                    raise _KeinKiSchluessel("Kein GLM-Key für ausführliche Endanalysen konfiguriert")
                _record_hint_origins(entry, entry.get("ki_pruefhinweise") or [])
                payload = deepcopy(entry)
                if _current_short(entry, profile, settings) is None:
                    payload.pop("kurztest", None)
                    payload.pop("kurz_basis", None)
                answer = ai.analyse(payload, deep=True, comparison=comparison)
                _reset_report_redaction(entry)
                entry.update(bericht_markdown=answer["bericht_markdown"], top5_befund=answer,
                             top5_basis=basis, top5_comparison=deepcopy(comparison), top5_comparison_basis=basis,
                             analyse_at=now(),
                             analyse_model=prompts.prompt_model("abonnenten_top5", settings))
                if redaction is not None:
                    entry["bericht_redaktion_verlangt"] = True
                _clear_final_error(entry)
                store.save_task(run_id, entry)
            elif not entry.get("top5_comparison"):
                # Here `basis` was recomputed from exactly this comparison;
                # equality with the stored hash is the recovery proof.
                entry.update(top5_comparison=deepcopy(comparison), top5_comparison_basis=basis)
            _check_hints(entry, (entry.get("top5_befund") or {}).get("neue_pruefhinweise") or [], stage="top5")
            clarify(entry)
            if entry.get("ki_klaerung_gesperrt") or entry.get("hard_excluded"):
                _clear_final_error(entry)
                entry["endpruefung_status"] = "nicht_beurteilbar"
                store.save_task(run_id, entry)
                continue
            rank()
            review_report(entry)
            if entry.get("ki_klaerung_gesperrt"):
                entry["endpruefung_status"] = "nicht_beurteilbar"
                store.save_task(run_id, entry)
                continue
            entry["pdf_path"] = report_pdf(entry, run_id)
            entry.update(status="fertig", ki_fehler="", endpruefung_basis=basis,
                         endpruefung_pdf_basis=_final_pdf_basis(entry, basis), endpruefung_status="abgeschlossen",
                         endpruefung_at=now(), endpruefung_fehler="")
            if not _final_report_complete(entry, basis):
                raise LlmError("Endprüfung ohne belegten aktuellen PDF-/Hinweisabschluss")
        except (LlmBudgetError, LlmNoBalanceError, LlmRateLimitError, Angehalten, _KeinKiSchluessel):
            entry["endpruefung_status"] = "wartet"
            store.save_task(run_id, entry)
            raise
        except Exception as exc:
            entry.update(status="ki_fehler", ki_fehler=str(exc), endpruefung_status="ki_fehler",
                         endpruefung_fehler=str(exc))
            log(f"Endprüfung {entry['name']}: {exc}")
        store.save_task(run_id, entry)
    ranked = rank()
    comparison = _optional_comparison(ranked)
    complete = len(ranked) >= 5 and all(
        _final_report_complete(entry, top5_basis(entry, profile, settings, comparison)) for entry in ranked[:5])
    for entry in entries:
        if entry in ranked[:5] and not _final_report_complete(
                entry, top5_basis(entry, profile, settings, comparison)) and entry.get("endpruefung_status") == "abgeschlossen":
            entry["endpruefung_status"] = "wartet"  # changed comparison requires a current report
        store.save_task(run_id, entry)
    source_errors = any(source.get("status") != "fertig"
                        or source.get("abonnenten_katalog", {}).get("complete") is False
                        or source.get("abonnenten_auswahl_unbestaetigt") is True
                        for source in run.get("snapshot_quellen", {}).values())
    gaps = any(not entry.get("data_done") for entry in entries)
    trend_gaps = run.get("auswahl_modus") == "abo_zufluss_retdd_v1" and any(
        (entry.get("abo_trend") or {}).get("verified") is not True
        for entry in entries if entry.get("eligible") and entry.get("data_done"))
    unresolved_finalists = any(entry.get("review_pending") or entry.get("ki_klaerung_gesperrt") for entry in ranked[:5])
    final_status = "teilweise" if source_errors or gaps or trend_gaps or not complete or unresolved_finalists else "abgeschlossen"
    store.update(run_id, status=final_status, phase="ergebnis", finished_at=now(),
                 workflow_abgeschlossen=complete and not unresolved_finalists,
                 daten_vollstaendig=not (source_errors or gaps or trend_gaps),
                 detail=f"{len(entries)} Anbieter bearbeitet; {len(ranked)} Kandidaten; "
                        f"{sum(_final_report_complete(entry, top5_basis(entry, profile, settings, comparison)) for entry in ranked[:5])} "
                        "ausführliche Endanalysen abgeschlossen; Kurz-KI optional"
                        + (f"; nur {len(ranked)} belegte Kandidaten für fünf Endanalysen" if len(ranked) < 5 else "")
                        + ("; Quellen-, Daten- oder Trendlücken bleiben ausgewiesen" if source_errors or gaps or trend_gaps else ""))


def _derive_legacy_export_receipt(entry, *, original_run_id):
    """Recognise the former strict native receipt on the NEW copy only.

    A matching receipt plus the exact immutable parsed export establishes its
    available export window, never a platform-wide or current-history claim.
    """
    if "trade_history_complete" in entry:
        return False  # do not overrule a later explicit false/unknown result
    refresh, stats = entry.get("refresh"), entry.get("quellen_stats")
    if not isinstance(refresh, dict) or not isinstance(stats, dict):
        return False
    version = str(entry.get("quelle_version") or "").strip().lower()
    if (not version or str(refresh.get("providerId")) != str(entry.get("id"))
            or refresh.get("version") != version or refresh.get("platformRefreshed") is not True
            or refresh.get("fullHistory") is not True
            or not isinstance(refresh.get("jobId"), str) or not refresh["jobId"].strip()
            or not isinstance(refresh.get("refreshedAt"), str) or not refresh["refreshedAt"].strip()):
        return False
    errors = refresh.get("tradelistenFehler", refresh.get("errors"))
    aborted = refresh.get("tradelistenAbgebrochen", refresh.get("aborted"))
    if type(errors) is not int or errors != 0 or aborted is not False:
        return False
    if (any(type(refresh[key]) is not int or refresh[key] != 0 for key in ("tradelistenFehler", "errors") if key in refresh)
            or any(refresh[key] is not False for key in ("tradelistenAbgebrochen", "aborted") if key in refresh)):
        return False
    if (any(stats.get(key) is False for key in (
            "quelle_trade_history_complete", "quelle_trades_history_complete", "trade_history_complete", "trades_history_complete"))
            or bool(stats.get("quelle_trades_gekappt")) or bool(stats.get("trades_truncated"))
            or bool(stats.get("quelle_trade_history_quality_reasons"))):
        return False
    count = entry.get("trades")
    if type(count) is not int or count < 0:
        return False
    try:
        from datetime import datetime
        from . import parser
        measured_at = datetime.fromisoformat(refresh["refreshedAt"].replace("Z", "+00:00"))
        if measured_at.tzinfo is None or measured_at.utcoffset() is None:
            return False
        db.verify_trade_file(entry["trades_path"], entry["trades_sha256"])
        parsed = parser.load_export(entry["trades_path"])
        if len(parsed.trades) != count:
            return False
    except (OSError, ValueError, TypeError, KeyError):
        return False
    entry.update(trade_history_complete=True, trade_history_status="vollstaendig",
                 trades_snapshot_complete_export=True,
                 trade_history_reason="Übernommener früherer nativer Full-History-Beleg: Anbieter/Version, fehlerfreier Job, "
                                      "unveränderter SHA-Snapshot und Parseranzahl geprüft; voller damals verfügbarer Export, "
                                      "keine Aussage über globale Plattformhistorie oder neue Frische.",
                 trade_history_beleg={"herkunft": "historischer_nativer_refresh_mit_snapshotpruefung",
                                      "ursprung_lauf_id": original_run_id, "refresh": deepcopy(refresh),
                                      "trades_sha256": entry["trades_sha256"], "parser_trades": count,
                                      "geprueft_am": now(), "native_messzeit": refresh["refreshedAt"]})
    return True


def _data_attempt_reusable(entry, common, exclusions):
    if (not entry.get("data_done") or entry.get("abgebrochen") is True
            or entry.get("data_basis") != eintrag_basis(entry, common, exclusions)):
        return False
    if entry.get("auswertung_typ") == "quellenprofitabilitaet":
        return True  # source values remain explicitly distinct from measured DD
    if entry.get("trade_history_complete") is not True:
        return False  # an old successful measurement is not a native full-history receipt
    try:
        db.verify_trade_file(entry["trades_path"], entry["trades_sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    # Older research runs stopped before H1 measurement below 2 months/50
    # trades. These completed research attempts are not complete data results.
    return bool(entry.get("equity")) and (
        _finite(entry.get("equity_dd_pct")) or (entry.get("equity") or {}).get("status") == "ok")


def _finish_data_job(store, run, entries, *, imported=False):
    rank_datamodus(entries, run["retdd_gewicht"])
    for entry in entries:
        source_values = entry.get("auswertung_typ") == "quellenprofitabilitaet"
        entry["daten_status"] = ("quellenwerte" if source_values else
                                 "vollstaendig" if entry.get("data_done") and entry.get("trade_history_complete") is True
                                 else "datenluecke")
        store.save_task(run["id"], entry)
    source_errors = any((run.get("snapshot_quellen") or {}).get(source, {}).get("status") != "fertig"
                        or (run.get("snapshot_quellen") or {}).get(source, {}).get("abonnenten_katalog", {}).get("complete") is False
                        or (run.get("snapshot_quellen") or {}).get(source, {}).get("abonnenten_auswahl_unbestaetigt") is True
                        for source in run["quellen"])
    gaps = any(not entry.get("data_done") or entry.get("auswertung_typ") == "quellenprofitabilitaet"
               or entry.get("trade_history_complete") is not True for entry in entries)
    trend_gaps = any((entry.get("abo_trend") or {}).get("verified") is not True
                     or not _finite((entry.get("abo_trend") or {}).get("delta_7")) for entry in entries)
    full = bool(entries) and not (source_errors or gaps or trend_gaps)
    completed = not imported or full
    status = "abgeschlossen" if full else "teilweise"
    models = [entry.get("modell") or {} for entry in entries]
    model_count = sum(bool(model) for model in models)
    model_dd = sum(_finite(model.get("equity_dd_pct")) for model in models)
    model_retdd = sum(_finite(model.get("retdd_jahr")) for model in models)
    model_capital = sum(_finite(model.get("startkapital_usd")) and model["startkapital_usd"] > 0 for model in models)
    store.update(run["id"], status=status, daten_status=status, phase="daten_ergebnis", finished_at=now(),
                 daten_workflow_abgeschlossen=completed, workflow_abgeschlossen=completed,
                 daten_vollstaendig=full, daten_uebernommen=imported,
                 daten_anzahl_anbieter=len(entries), daten_anzahl_mit_dd=sum(_finite(entry.get("equity_dd_pct")) for entry in entries),
                 daten_anzahl_mit_retdd=sum(_finite(entry.get("retdd_jahr")) for entry in entries),
                 modell_anzahl_mit_dd=model_dd, modell_anzahl_mit_retdd=model_retdd,
                 modell_anzahl_mit_startkapital=model_capital,
                 modell_anzahl_berechnet=sum(model.get("status") == "berechnet" for model in models),
                 modell_vollstaendig=bool(entries) and all(model.get("status") == "berechnet"
                      and entry.get("trade_history_complete") is True for entry, model in zip(entries, models)),
                 detail=f"{len(entries)} ausgewählte Anbieter in der Datentabelle; "
                        f"{sum(_finite(entry.get('equity_dd_pct')) for entry in entries)} mit gemessenem Equity-DD; "
                        f"{sum(_finite(entry.get('retdd_jahr')) for entry in entries)} mit RetDD; "
                        + (f"Modellszenario: {model_capital} Kapitalbasen, {model_dd} Floating-DD, {model_retdd} RetDD; "
                           if model_count else "")
                        +
                        "kein KI-, Top-5- oder PDF-Schritt"
                        + ("; Quellen-, Trade-, Mess- oder Trendlücken bleiben ausdrücklich ausgewiesen" if not full else "")
                        + ("; gespeicherter Originalstand übernommen, keine neue Datenbeschaffung" if imported else ""))


def _execute_model_only(store, run_id, settings):
    """Local scenario computation cannot refresh sources or start terminals."""
    from .abonnenten_modellworkflow import berechne_bestand
    run = store.read(run_id)
    log = lambda message: store.log(run_id, message)
    stopped = lambda: bool(store.read(run_id).get("stop_requested"))
    try:
        import psutil
        store.update(run_id, status="laeuft", daten_status="laeuft", phase="kapitalmodell",
                     pid=os.getpid(), process_start=psutil.Process().create_time(), stop_requested=False,
                     fehler="", modell_abgeschlossen=False,
                     daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False)
        entries = _arbeitsreihenfolge(store.tasks(run_id), run["quellen"])
        berechne_bestand(store, run, entries, log, stopped)
        if stopped():
            raise Angehalten("Modellberechnung angehalten")
        _finish_data_job(store, run, entries)
    except Angehalten as exc:
        store.update(run_id, status="angehalten", daten_status="angehalten", detail=str(exc),
                     modell_abgeschlossen=False, daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False)
    except Exception as exc:
        store.update(run_id, status="teilweise", daten_status="fehler",
                     detail="Modellberechnung unterbrochen; gespeicherte Ergebnisse bleiben erhalten.",
                     fehler=f"{type(exc).__name__}: {exc}", modell_abgeschlossen=False,
                     daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False)


def _execute_data_only(store, run_id, settings):
    from .abonnenten_analyse_daten import AnalyseDaten
    from .abonnenten_analyse_trend import freeze_trends
    run = store.read(run_id)
    if not run or run.get("workflow_modus") != DATA_WORKFLOW_MODE:
        raise ValueError("Ausführung ohne KI benötigt einen ausdrücklich angelegten Datenauftrag")
    if run.get("modell_nur_bestand"):
        _execute_model_only(store, run_id, settings)
        return
    log = lambda message: store.log(run_id, message)
    stopped = lambda: bool(store.read(run_id).get("stop_requested"))
    settings = {**settings, "abonnenten_daten_ohne_ki": True}
    try:
        import psutil
        store.update(run_id, status="laeuft", daten_status="laeuft", phase="quellen_aktualisieren",
                     pid=os.getpid(), process_start=psutil.Process().create_time(), stop_requested=False,
                     fehler="", daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False)
        prior_sources = deepcopy(run.get("snapshot_quellen") or {})
        _snapshot(store, run, settings, log, stopped)
        run = store.read(run_id)
        references = deepcopy(run.get("abo_quellen_referenz") or {})
        reference_history = deepcopy(run.get("abo_quellen_referenz_historie") or [])
        for source in run["quellen"]:
            if (source in references and prior_sources.get(source, {}).get("status") != "fertig"
                    and run.get("snapshot_quellen", {}).get(source, {}).get("status") == "fertig"):
                reference_history.append({"quelle": source, "referenz": references.pop(source),
                                          "ersetzt_am": now(), "grund": "Zuvor fehlgeschlagene Quelle im neuen Datenauftrag erfolgreich ausgewählt"})
        if references != (run.get("abo_quellen_referenz") or {}):
            run.update(abo_quellen_referenz=references, abo_quellen_referenz_historie=reference_history)
            store.update(run_id, abo_quellen_referenz=references, abo_quellen_referenz_historie=reference_history)
        entries = _arbeitsreihenfolge(store.tasks(run_id), run["quellen"])
        common, exclusions = daten_basis(settings), _restart_exclusions()
        with AnalyseDaten(settings, log=log) as provider:
            store.update(run_id, phase="trades_und_equity")
            for entry in entries:
                if stopped():
                    raise Angehalten("Stop angefordert")
                if _data_attempt_reusable(entry, common, exclusions):
                    continue
                entry.update(status="rechnet", daten_status="laeuft", grund="", data_done=False, abgebrochen=False)
                store.save_task(run_id, entry)
                log(f"Daten und vollständige verfügbare Tradeliste: {entry['quelle']} · {entry['name']}")
                try:
                    result = provider.berechne(entry, should_stop=stopped)
                    entry.update(result)
                    entry.update(data_done=bool(result.get("data_complete")),
                                 data_basis=eintrag_basis(entry, common, exclusions))
                    if entry.get("abgebrochen") or stopped():
                        raise Angehalten("Datenbeschaffung angehalten")
                    if (entry["quelle"], entry["id"]) in exclusions:
                        entry.update(eligible=False, hard_excluded=True,
                                     grund="Explizite Ausschlussliste: " + str(exclusions[(entry["quelle"], entry["id"])].get("grund") or "Ausschluss"))
                    if run["dd_grenze"] is not None and _finite(entry.get("equity_dd_pct")) and entry["equity_dd_pct"] > run["dd_grenze"]:
                        entry.update(eligible=False, grund=f"Gewählte Equity-DD-Grenze {run['dd_grenze']:g} % überschritten")
                    entry["status"] = ("datenluecke" if not entry["data_done"] else
                                       "quellenwerte" if entry.get("auswertung_typ") == "quellenprofitabilitaet" else
                                       "ausgeschlossen" if entry.get("hard_excluded") else "fertig")
                    entry["daten_status"] = ("vollstaendig" if entry["data_done"]
                                             and entry.get("trade_history_complete") is True else "datenluecke")
                except Angehalten:
                    entry.update(status="datenluecke", daten_status="angehalten", data_done=False, abgebrochen=True)
                    store.save_task(run_id, entry)
                    raise
                except Exception as exc:
                    entry.update(status="datenluecke", daten_status="datenluecke", data_done=False,
                                 eligible=False, grund=f"{type(exc).__name__}: {exc}")
                store.save_task(run_id, entry)
        if stopped():
            raise Angehalten("Stop angefordert")
        _freeze_source_means(store, run_id, run, entries)
        store.update(run_id, phase="abonnenten_trends")
        freeze_trends(store, run_id, entries, settings, log, stopped, include_all=True)
        if stopped():
            raise Angehalten("Stop angefordert")
        if run.get("kapitalmodell_aktiv"):
            from .abonnenten_modellworkflow import berechne_bestand
            store.update(run_id, phase="kapitalmodell")
            berechne_bestand(store, run, entries, log, stopped)
        _finish_data_job(store, run, entries)
    except Angehalten as exc:
        store.update(run_id, status="angehalten", daten_status="angehalten", detail=str(exc),
                     daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False)
    except Exception as exc:
        store.update(run_id, status="teilweise", daten_status="fehler", detail="Datenlauf unterbrochen; gespeicherte Daten bleiben erhalten",
                     fehler=f"{type(exc).__name__}: {exc}", daten_workflow_abgeschlossen=False, workflow_abgeschlossen=False)


def _execute(store, run_id, settings):
    run = store.read(run_id)
    if run and run.get("workflow_modus") == DATA_WORKFLOW_MODE:
        _execute_data_only(store, run_id, settings)
        return
    from .abonnenten_analyse_daten import AnalyseDaten
    log = lambda message: store.log(run_id, message)
    stopped = lambda: bool(store.read(run_id).get("stop_requested"))
    try:
        parallelitaet = _ki_parallelitaet(run, settings)
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
                     ki_parallelitaet=parallelitaet, ki_aktive_slots=0,
                     budget_applied={key: settings[key] for key in BUDGET_SETTING_KEYS if key in settings})
        if run.get("kurztest_optional"):
            store.update(run_id, workflow_abgeschlossen=False)
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
                    if entry.get("kurztest") or entry.get("bericht_markdown") or entry.get("ki_pruefentscheidungen"):
                        entry.setdefault("previous_results", []).append({k: entry.get(k) for k in (
                            "trades_sha256", "data_basis", "kurztest", "kurz_basis", "bericht_markdown",
                            "top5_basis", "top5_befund", "pdf_path", "retdd_jahr", "equity_dd_pct",
                            "review_pending", "ki_pruefhinweise", "ki_pruefhinweis_quellen", "ki_hinweisstatus",
                            *_FINAL_REVIEW_FIELDS)})
                        for key in ("kurztest", "kurz_basis", "bericht_markdown", "top5_basis", "pdf_path",
                                    "review_pending", "ki_pruefhinweise", "ki_pruefhinweis_quellen",
                                    "ki_hinweisstatus", "top5_befund", *_FINAL_REVIEW_FIELDS):
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
        if run.get("kurztest_optional"):
            _execute_optional_finalists(store, run_id, run, entries, settings, profile, log, stopped)
            return
        ranked = rank_entries(entries, run["retdd_gewicht"])
        for entry in entries:
            store.save_task(run_id, entry)
        if stopped():
            raise Angehalten("Stop angefordert")
        store.update(run_id, phase="kurzanalysen")
        pending_short = _kurzanalysen(store, run_id, entries, settings, profile, stopped, log, parallelitaet)
        if pending_short:
            store.update(run_id, status="teilweise", phase="kurzanalysen", detail="Einzelne Kurzanalysen fehlen; fortsetzen möglich")
            return
        store.update(run_id, phase="top5_analysen")
        ai = AnalyseKI(store, run_id, settings, profile, should_stop=stopped, log=log)
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
                    if not ai.client.has_key:
                        raise _KeinKiSchluessel("Kein GLM-Key konfiguriert; Berechnungen und Kurzberichte bleiben erhalten. "
                                               "Unter Einstellungen ergänzen und fortsetzen.")
                    _record_hint_origins(entry, entry.get("ki_pruefhinweise") or [])
                    answer = ai.analyse(entry, deep=True, comparison=comparison)
                    _reset_report_redaction(entry)
                    entry.update(bericht_markdown=answer["bericht_markdown"], top5_befund=answer,
                                 top5_basis=basis, top5_comparison=deepcopy(comparison), top5_comparison_basis=basis,
                                 analyse_at=now(),
                                 analyse_model=prompts.prompt_model("abonnenten_top5", settings))
                    _clear_final_error(entry)
                _check_hints(entry, (entry.get("top5_befund") or {}).get("neue_pruefhinweise") or [], stage="top5")
                entry["status"] = "ausgeschlossen" if entry.get("hard_excluded") else "fertig"
                store.save_task(run_id, entry)  # preserve paid response before PDF work
                entry["pdf_path"] = report_pdf(entry, run_id)
                entry["ki_fehler"] = ""
            except (LlmBudgetError, LlmNoBalanceError, LlmRateLimitError, Angehalten, _KeinKiSchluessel):
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
                            or q.get("abonnenten_auswahl_unbestaetigt") is True
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
    except LlmRateLimitError as exc:
        store.update(run_id, status="wartet_anbieter", detail=str(exc), fehler=str(exc))
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
            if kind == "top5" and isinstance(entry.get("top5_comparison"), list):
                record["herkunft"]["vergleich"] = deepcopy(entry["top5_comparison"])
                record["herkunft"]["vergleich_basis"] = entry.get("top5_comparison_basis") or entry.get("top5_basis")
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
    from .abonnenten_analyse_klaerung import has_current_resolution
    if has_current_resolution(entry):
        entry["review_pending"] = False
        if entry.get("ki_klaerung_gesperrt"):
            for field in ("rang", "auswahlwert", "retdd_perzentil"):
                entry[field] = None
        return
    if entry.get("ki_pruefentscheidungen"):
        # Old conclusions remain auditable but cannot clear new/changed hints.
        entry["ki_klaerung_gesperrt"] = False
        entry["ki_klaerung_status"] = "veraltet"
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
