"""Dialog und Vergleich eines gespeicherten Abonnenten-Rechercheauftrags.

Nur ein bewusster Start/Fortsetzen löst Arbeit aus. Das Lesen von Fortschritt
und Ergebnissen startet keine Beschaffung, Berechnung oder Modellaufrufe.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from importlib import import_module
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from . import config, db, quellen, scan_worker
from .llm import prompts


def _backend():
    return import_module("mqlkiscanner.abonnenten_analyse")


def _zeitpunkt(value) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


@st.cache_data(ttl=4, max_entries=32, show_spinner=False)
def _quellenstatus(quelle: dict, run_id: str, provider_id: str,
                  version: str, seit: str) -> dict | None:
    """Nur GET; ein fremder, alter oder fertiger Job ist kein Livefortschritt.

    Lauf und Versuchsbeginn gehören zum Cache-Schlüssel. Zugangsdaten werden
    erst im bestehenden Client gelesen und gelangen nicht in den Cache.
    """
    try:
        status = quellen.client_fuer_quelle(quelle, timeout=1.0).update_status()
        result = status.get("ergebnis")
        if (status.get("state") != "running" or not status.get("jobId")
                or status.get("finishedAt") or not isinstance(result, dict)
                or str(result.get("providerId") or "") != provider_id
                or result.get("version") != version):
            return None
        started, expected = _zeitpunkt(status.get("startedAt")), _zeitpunkt(seit)
        # Der Auftragslog ist sekundengenau, native Clients teils ebenfalls.
        if started is None or expected is None or started < expected - 2:
            return None
        return {**status, "gelesen_um": datetime.now().astimezone().strftime("%H:%M:%S")}
    except Exception:
        # Eine zusätzliche Leseanzeige darf einen laufenden Auftrag weder
        # stören noch Verbindungsprobleme als dessen Fehler ausgeben.
        return None


def _laufender_quellenfortschritt(state: dict, *, aktueller_lauf: bool) -> dict | None:
    if (not aktueller_lauf or not state.get("laeuft") or state.get("status") != "laeuft"
            or state.get("phase") != "trades_und_equity"):
        return None
    active = [entry for entry in state.get("entries", [])
              if entry.get("status") == "rechnet" and not entry.get("data_done")]
    if len(active) != 1:
        return None  # Unterbrochene/mehrdeutige alte Tasks nicht als aktiv raten.
    entry = active[0]
    try:
        provider_id = str(int(entry["id"]))
        if isinstance(entry["id"], bool) or int(provider_id) <= 0:
            return None
        quelle = db.get_quelle(int(entry["quelle_id"]))
        if (not quelle or not quelle.get("aktiv") or not entry.get("quellen_uid")
                or str(quelle.get("quellen_uid") or "") != str(entry["quellen_uid"])
                or db.kanonische_quelle(quelle["kuerzel"]) != entry.get("quelle")):
            return None
        version = str(entry.get("quelle_version") or "").strip().lower()
        if version not in {"mql4", "mql5", "pelican", "vantage", "zulu", "rst"}:
            return None
        status = _quellenstatus(quelle, str(state["id"]), provider_id, version,
                               str(state.get("updated_at") or state.get("created_at") or ""))
        return dict(status, quelle=entry["quelle"], provider_id=provider_id) if status else None
    except Exception:
        return None


def _render_quellenfortschritt(state: dict, *, aktueller_lauf: bool) -> None:
    status = _laufender_quellenfortschritt(state, aktueller_lauf=aktueller_lauf)
    if not status:
        return
    done, total = _number(status.get("done")), _number(status.get("total"))
    count = (f" · {int(done):,}/{int(total):,}".replace(",", ".")
             if done is not None and total is not None and done >= 0 and total > 0 else "")
    st.caption(f"Quellenclient · {status['quelle']}:{status['provider_id']} · "
               f"{status.get('phase') or 'läuft'}{count} · {status.get('message') or ''} · "
               f"Job {status['jobId']} · Status gelesen {status['gelesen_um']}")
    if done is not None and total is not None and done >= 0 and total > 0:
        st.progress(min(1.0, done / total))


def _ki_zaehler(state: dict, backend) -> dict:
    """Gespeicherte Ergebnisse zählen; keine neue fachliche Bewertung."""
    possible = getattr(backend, "_ki_possible", None)

    def vorgesehen(entry):
        if callable(possible):
            return bool(possible(entry))
        # Dieselben reinen Felder für ältere/fakebare UI-Backends.
        return bool(entry.get("trades_path") and entry.get("forensik")
                    and (_number(entry.get("trades")) or 0) >= 50
                    and (_number(entry.get("dauer_monate")) or 0) >= 2)

    entries = list(state.get("entries") or [])
    short = [entry for entry in entries if vorgesehen(entry)]
    top = [entry for entry in entries if not _quellenprofitabilitaet(entry)
           and (rank := _number(entry.get("rang"))) is not None and 1 <= rank <= 5]
    return {"kurz_fertig": sum(isinstance(entry.get("kurztest"), dict) and bool(entry["kurztest"])
                               for entry in short),
            "kurz_gesamt": len(short),
            "top5_fertig": sum(bool(str(entry.get("bericht_markdown") or "").strip()) for entry in top),
            "top5_gesamt": len(top),
            "fehler": sum(bool(entry.get("ki_fehler")) or entry.get("status") == "ki_fehler"
                           for entry in entries if not _quellenprofitabilitaet(entry))}


def _meldungszeit(state: dict) -> str | None:
    detail = str(state.get("detail") or "")
    for line in reversed(state.get("logs") or []):
        stamp, _, message = str(line).partition(" ")
        if message == detail and _zeitpunkt(stamp) is not None:
            return stamp
    return None  # updated_at kann allein durch einen Phasenwechsel neuer sein.


def _letzte_ki_reservierung(state: dict, backend, *, aktueller_lauf: bool) -> str | None:
    """Letzter Ledger-Eintrag, kein Nachweis eines laufenden HTTP-Aufrufs."""
    if (not aktueller_lauf or not state.get("laeuft") or state.get("status") != "laeuft"
            or state.get("phase") not in {"kurzanalysen", "top5_analysen"}):
        return None
    store_type = getattr(backend, "Store", None)
    if not callable(store_type):
        return None
    try:
        # Store() legt beim Lesen keine Datenbank an; ausschließlich SELECT.
        with store_type().connection() as connection:
            row = connection.execute(
                "SELECT status,created_at FROM calls WHERE run_id=? ORDER BY rowid DESC LIMIT 1",
                (state["id"],)).fetchone()
        if row and row["status"] == "reserved" and _zeitpunkt(row["created_at"]) is not None:
            return str(row["created_at"])
    except Exception:
        pass  # Die ergänzende Anzeige darf den Auftrag nicht stören.
    return None


def _render_ki_fortschritt(state: dict, backend, *, aktueller_lauf: bool) -> bool:
    if state.get("phase") not in {"kurzanalysen", "top5_analysen"}:
        return False
    counts = _ki_zaehler(state, backend)
    stage = "KI-Kurzanalysen" if state["phase"] == "kurzanalysen" else "Ausführliche Top-5-Analysen"
    st.caption(f"Arbeitsschritt dieses Auftrags: {stage} · {state.get('status') or ''}")
    with st.container(horizontal=True):
        st.metric("KI-Kurztests vorhanden", f"{counts['kurz_fertig']}/{counts['kurz_gesamt']}",
                  help="Gespeicherte Kurztests der dafür auswertbaren Anbieter. Quellenprofitabilität zählt nicht dazu.")
        st.metric("Top-5-Analysen vorhanden", f"{counts['top5_fertig']}/{counts['top5_gesamt']}",
                  help="Gespeicherte ausführliche Berichte der derzeitigen Top 5; PDF-Erstellung und Fehler bleiben getrennt.")
        st.metric("Anbieter mit KI-Fehler", str(counts["fehler"]))
        slots, parallel = state.get("ki_aktive_slots"), _parallelitaet_wert(state.get("ki_parallelitaet"))
        if (state["phase"] == "kurzanalysen" and aktueller_lauf and state.get("laeuft")
                and state.get("status") == "laeuft" and parallel is not None
                and type(slots) is int and 0 <= slots <= parallel):
            st.metric("Belegte KI-Plätze", f"{slots}/{parallel}",
                      help="Eingereihte, noch nicht vollständig übernommene Kurztest-Aufträge. "
                           "Die Zahl belegt keine aktiven HTTP-Anfragen.")
    key = "kurz" if state["phase"] == "kurzanalysen" else "top5"
    total, done = counts[f"{key}_gesamt"], counts[f"{key}_fertig"]
    st.progress(min(1.0, done / total) if total else 0.0)
    st.caption("Diese Zähler betreffen gespeicherte KI-Ergebnisse. Der Anbieter-Endstand enthält "
               "auch Quellenwerte, Ausschlüsse und Datenlücken und ist kein KI-Fortschritt.")
    if reserved := _letzte_ki_reservierung(state, backend, aktueller_lauf=aktueller_lauf):
        st.caption(f"Letzter KI-Arbeitsschritt reserviert seit {reserved}. "
                   "Die gespeicherte Reservierung belegt keinen aktuell laufenden Netzaufruf.")
    return True


def _defaults(settings: dict) -> tuple[float, float | None]:
    weight = settings.get("abonnenten_analyse_retdd_gewicht", 70.0)
    limit = settings.get("abonnenten_analyse_dd_grenze")
    try:
        weight = float(weight)
        if not math.isfinite(weight) or not 0 <= weight <= 100:
            weight = 70.0
    except (TypeError, ValueError):
        weight = 70.0
    try:
        limit = float(limit) if limit is not None else None
        if limit is not None and (not math.isfinite(limit) or limit <= 0):
            limit = None
    except (TypeError, ValueError):
        limit = None
    return weight, limit


def _parallelitaet_wert(value) -> int | None:
    return value if type(value) is int and 1 <= value <= 10 else None


def _parallelitaet_input(settings: dict, prefix: str) -> int:
    parallel = st.number_input(
        "KI-Kurzanalysen gleichzeitig", min_value=1, max_value=10, step=1,
        value=_parallelitaet_wert(settings.get("abonnenten_analyse_parallelitaet")) or 10,
        key=f"{prefix}_parallelitaet")
    st.caption(f"Bis zu {parallel} KI-Kurzanalysen gleichzeitig; der KI-Anbieter kann drosseln.")
    return int(parallel)


def _policy_inputs(settings: dict, prefix: str) -> tuple[float, float | None]:
    weight, limit = _defaults(settings)
    limited = st.toggle("Drawdown-Grenze verwenden", value=limit is not None,
                        key=f"{prefix}_dd_aktiv",
                        help="Standard: keine feste DD-Grenze in dieser Rechercheliste.")
    dd = (st.number_input("Maximaler gemessener Equity-DD (%)", min_value=0.1,
                          value=limit or 50.0, step=1.0, key=f"{prefix}_dd")
          if limited else None)
    if not limited:
        st.caption("Drawdown-Grenze: keine. Die Effizienz wird über RetDD beurteilt.")
    retdd = st.slider("Gewicht Jahres-RetDD (%)", min_value=0.0,
                      max_value=100.0, value=weight, step=1.0,
                      key=f"{prefix}_retdd")
    st.caption(f"RetDD {retdd:g} % · relativer Abonnentenrang {100 - retdd:g} %. "
               "Gewichtet werden Perzentile, keine absoluten Abonnentenzahlen.")
    return float(retdd), dd


def render_defaults_editor(settings: dict) -> None:
    """Eigener Speicherbereich, ohne andere Einstellungsgruppen zu überschreiben."""
    with st.expander("Standard für die Abonnentenanalyse", expanded=False):
        weight, limit = _policy_inputs(settings, "admin_abonnenten_analyse")
        parallel = _parallelitaet_input(settings, "admin_abonnenten_analyse")
        st.caption("Top 200 je Quelle, mindestens 1 Abonnent · 2 Monate und 50 Trades · "
                   "Kurztest für alle auswertbaren Strategien, Vollbericht für die besten 5.")
        if st.button("Analyse-Standard speichern", key="admin_abonnenten_standard",
                     icon=":material/save:"):
            config.save_settings({**config.load_settings(),
                                  "abonnenten_analyse_retdd_gewicht": weight,
                                  "abonnenten_analyse_dd_grenze": limit,
                                  "abonnenten_analyse_parallelitaet": parallel})
            st.success("Standard für neue Rechercheaufträge gespeichert.")


def _close_dialog() -> None:
    st.session_state["_abonnenten_analyse_dialog_offen"] = False


@st.dialog("Strategien bewerten", width="medium", on_dismiss=_close_dialog)
def analyse_dialog() -> None:
    settings = config.load_settings()
    sources = db.list_quellen(nur_aktiv=True)
    labels = {str(q["kuerzel"]): quellen.anzeige_name(q) for q in sources}
    if not labels:
        st.warning("Keine aktive Datenquelle. Unter Einstellungen → Datenquellen ergänzen.")
        return
    st.selectbox("Welche Strategien?", ["Top 200 je Quelle, mindestens 1 Abonnent"],
                 disabled=True, key="abonnenten_analyse_umfang")
    saved = settings.get("abonnenten_analyse_quellen")
    default_sources = ([q for q in saved if q in labels]
                       if isinstance(saved, list) else list(labels))
    chosen = st.multiselect("Welche Quellen?", list(labels), default=default_sources,
                            format_func=lambda key: labels[key],
                            key="abonnenten_analyse_quellen")
    weight, limit = _policy_inputs(settings, "abonnenten_analyse_start")
    parallel = _parallelitaet_input(settings, "abonnenten_analyse_start")
    st.info("Mindestens 2 Monate und 50 abgeschlossene Trades. Fehlende Daten werden "
            "automatisch geladen. Kurz-KI für alle auswertbaren Strategien; "
            "ausführliche Analyse für die besten 5. Budget aus den Einstellungen.")
    st.caption("Eigene Rechercheliste: Die bestehende Workflow-Ampel wird nicht geändert. "
               "Ein Recherchekandidat ist keine Handelsfreigabe.")
    save = st.checkbox("Diese Auswahl als Standard speichern",
                        key="abonnenten_analyse_standard")
    missing = prompts.fehlende_vorlagen(prompts.ABONNENTEN_PROMPT_KEYS)
    if missing:
        st.error("Analysevorlagen fehlen oder sind leer: " + ", ".join(missing)
                 + ". Unter Einstellungen → Analysevorlagen wiederherstellen.")
    if st.button("Analyse starten", type="primary", icon=":material/play_arrow:",
                 key="abonnenten_analyse_start", disabled=not chosen or bool(missing)):
        try:
            if scan_worker.active_run() is not None:
                st.warning("Es läuft bereits ein Scan oder Studien-Batch. Danach starten.")
                return
            backend = _backend()
            if backend.zustand().get("laeuft"):
                st.warning("Eine Abonnentenanalyse läuft bereits. Fortschritt unten öffnen.")
                return
            run_id = backend.starten(chosen, settings={**settings, "abonnenten_analyse_parallelitaet": parallel},
                                     retdd_gewicht=weight, dd_grenze=limit)
            if not run_id:
                st.error("Der Analyseauftrag konnte nicht gestartet werden.")
                return
            st.session_state["abonnenten_analyse_lauf"] = run_id
        except Exception as exc:
            st.error(f"Analyse nicht gestartet: {exc}")
            return
        if save:
            try:
                config.save_settings({**config.load_settings(),
                                      "abonnenten_analyse_retdd_gewicht": weight,
                                      "abonnenten_analyse_dd_grenze": limit,
                                      "abonnenten_analyse_parallelitaet": parallel,
                                      "abonnenten_analyse_quellen": chosen})
            except Exception as exc:
                st.session_state["_abonnenten_analyse_notice"] = (
                    f"Analyse gestartet. Der neue Standard konnte nicht gespeichert werden: {exc}")
        _close_dialog()
        st.rerun()


def render_start_button() -> None:
    if st.button("Strategien bewerten", key="abonnenten_analyse_oeffnen",
                 type="primary", icon=":material/query_stats:"):
        st.session_state["_abonnenten_analyse_dialog_offen"] = True
    if st.session_state.get("_abonnenten_analyse_dialog_offen"):
        analyse_dialog()


def _quellenprofitabilitaet(entry: dict) -> bool:
    return entry.get("auswertung_typ") == "quellenprofitabilitaet"


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _quellrendite_zeitraum(entry: dict) -> str:
    months = _number(entry.get("rendite_quelle_monate"))
    if months is None or months < 0:
        return "Zeitraum unbekannt"
    if months == 0:
        return "Gesamtzeitraum laut Quelle"
    return f"{months:g} {'Monat' if months == 1 else 'Monate'} laut Quelle"


def _finanzdatenstand(entry: dict) -> str:
    return str(entry.get("finanzdaten_stand") or "unbekannt – kein Quellenstand angegeben")


def _quellen_messhinweis(entry: dict) -> str:
    return str(entry.get("messhinweis_quelle") or entry.get("messhinweisQuelle")
               or entry.get("messhinweis") or "")


def _basisbewertung(entry: dict) -> str:
    profit = {"positiv": "Quellengewinn positiv", "negativ": "Quellengewinn negativ",
              "unveraendert": "Quellengewinn unverändert",
              "unbekannt": "Quellengewinn nicht bestimmbar"}.get(
                  entry.get("profitabilitaet"), "Quellengewinn nicht bestimmbar")
    return profit + "; RetDD nicht bestimmbar, da kein eigener gemessener Equity-DD vorliegt."


def _abo_positionen(entry: dict) -> list[int]:
    values = entry.get("abo_ausgelassene_positionen")
    return (sorted({value for value in values if isinstance(value, int)
                    and not isinstance(value, bool) and value > 0})
            if isinstance(values, list) else [])


def _abo_auswahlhinweis(entry: dict) -> str:
    if entry.get("abo_referenz_vollstaendig") is not False:
        return ""
    count = len(_abo_positionen(entry))
    skipped = (f"{count} API-Position{'en' if count != 1 else ''} ausgelassen. "
               if count else "")
    reference = _number(entry.get("abo_referenz_n"))
    basis = f"{int(reference)} erfassten Anbietern" if reference is not None and reference > 0 else "den erfassten Anbietern"
    return (f"Vorläufige Abonnentenauswahl: {skipped}Vollständige Top 200 nicht belegt. "
            f"Der Abonnentenrang gilt innerhalb von {basis}.")


def _mit_abo_auswahl(entry: dict, state: dict) -> dict:
    """Auch der eingefrorene Quellenbeleg bleibt in Ansicht/Export sichtbar."""
    catalog = ((state.get("snapshot_quellen") or {}).get(entry.get("quelle")) or {}).get("abonnenten_katalog")
    if not isinstance(catalog, dict) or catalog.get("complete") is not False:
        return entry
    return {**entry, "abo_referenz_vollstaendig": False,
            "abo_ausgelassene_positionen": catalog.get("skipped_positions", entry.get("abo_ausgelassene_positionen")),
            "abo_katalog_geprueft": catalog.get("scanned_providers", entry.get("abo_katalog_geprueft"))}


def ergebnis_tabelle(entries: list[dict]) -> pd.DataFrame:
    """Eine Tabellenbasis für Anzeige und Export; unbekannte Zahlen bleiben leer."""
    rows = []
    for e in entries:
        source_values = _quellenprofitabilitaet(e)
        short = e.get("kurztest") if isinstance(e.get("kurztest"), dict) else {}
        rows.append({
            "Rang": None if source_values else e.get("rang"), "Strategie": e.get("name"),
            "Quelle": e.get("quelle"), "ID": e.get("id"),
            "Auswahlwert": None if source_values else e.get("auswahlwert"),
            "Jahres-RetDD": None if source_values else e.get("retdd_jahr"),
            "RetDD-Perzentil": None if source_values else e.get("retdd_perzentil"),
            "Equity-DD %": None if source_values else e.get("equity_dd_pct"),
            "Geom. %/Monat": None if source_values else e.get("ertrag_monat_geom_pct"),
            "Monate": e.get("dauer_monate"), "Trades": e.get("trades"),
            "Quellengewinn USD": _number(e.get("gewinn_usd")) if source_values else None,
            "Quellrendite %": _number(e.get("rendite_quelle_pct")) if source_values else None,
            "Renditezeitraum (Quelle)": _quellrendite_zeitraum(e) if source_values else "",
            "Quellrendite Monate": _number(e.get("rendite_quelle_monate")) if source_values else None,
            "Rating-Balance USD": _number(e.get("rating_balance_usd")) if source_values else None,
            "Quellenprofitabilität": e.get("profitabilitaet", "unbekannt") if source_values else "",
            "Finanzdatenstand (Quelle)": _finanzdatenstand(e) if source_values else "",
            "Quellenwerte gelesen am": e.get("daten_gelesen_am") if source_values else None,
            "Basisbewertung": _basisbewertung(e) if source_values else "",
            "Auswertungsart": e.get("auswertung_typ", ""),
            "Abonnenten": e.get("abonnenten"), "Abo-Perzentil": e.get("abo_perzentil"),
            "Abonnentenreferenz vollständig": (e.get("abo_referenz_vollstaendig")
                                                if isinstance(e.get("abo_referenz_vollstaendig"), bool) else None),
            "Ausgelassene API-Positionen": ", ".join(map(str, _abo_positionen(e))),
            "Geprüfte Kataloganbieter": e.get("abo_katalog_geprueft"),
            "Auswahlhinweis": _abo_auswahlhinweis(e),
            "Strategietyp": "" if source_values else short.get("strategietyp", ""),
            "Martingale": "" if source_values else short.get("martingale_einordnung", ""),
            "Prüfstatus": e.get("status", ""), "Grund": e.get("grund", ""),
            "KI-Kurzurteil": "" if source_values else short.get("kurzurteil", ""),
            "Vollbericht": "vorhanden" if e.get("bericht_markdown") and not source_values else "",
            "signal_ref": e.get("signal_ref", ""),
        })
    df = pd.DataFrame(rows)
    for column in ("Rang", "ID", "Auswahlwert", "Jahres-RetDD", "RetDD-Perzentil", "Equity-DD %",
                   "Geom. %/Monat", "Monate", "Trades", "Abonnenten", "Abo-Perzentil",
                   "Quellengewinn USD", "Quellrendite %", "Quellrendite Monate", "Rating-Balance USD",
                   "Geprüfte Kataloganbieter"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def ergebnis_csv(entries: list[dict], state: dict) -> bytes:
    df = ergebnis_tabelle([_mit_abo_auswahl(entry, state) for entry in entries])
    for label, key in {
        "Messhinweis": "messhinweis", "Handel von": "zeit_von", "Handel bis": "zeit_bis",
        "Trade-SHA256": "trades_sha256", "Katalogstand": "katalog_stand",
        "Abo-Referenzanzahl": "abo_referenz_n", "KI-Fehler": "ki_fehler",
        "KI-Hinweisstatus": "ki_hinweisstatus",
    }.items():
        df[label] = [entry.get(key) for entry in entries]
    df["Quellen-Messhinweis"] = [_quellen_messhinweis(entry) if _quellenprofitabilitaet(entry)
                                else "" for entry in entries]
    df["Lauf"] = state.get("id", "")
    df["RetDD-Gewicht %"] = state.get("retdd_gewicht")
    df["Abonnenten-Gewicht %"] = 100 - float(state.get("retdd_gewicht", 70))
    df["DD-Grenze %"] = state.get("dd_grenze")
    df["Laufstatus"] = state.get("status", "")
    # Anbietertexte dürfen beim Öffnen in Excel keine Formeln ausführen.
    for name in df.select_dtypes(include=["object", "string"]).columns:
        df[name] = df[name].map(lambda value: "'" + value if isinstance(value, str)
                               and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def _render_detail(entry: dict, run_id: str) -> None:
    identity = str(entry.get("signal_ref") or f"{entry.get('quelle')}:{entry.get('id')}")
    token = sha256((run_id + identity).encode()).hexdigest()[:16]
    st.markdown(f"**{entry.get('name') or 'Strategie'}** · {entry.get('quelle')}:{entry.get('id')}")
    if hint := _abo_auswahlhinweis(entry):
        st.warning(hint)
    if entry.get("grund"):
        st.caption(str(entry["grund"]))
    if _quellenprofitabilitaet(entry):
        st.markdown("**Basisbewertung aus Quellenwerten**")
        st.write(_basisbewertung(entry))
        with st.container(horizontal=True):
            for label, value in (("Gewinn laut Quelle (USD)", entry.get("gewinn_usd")),
                                 ("Rendite laut Quelle (%)", entry.get("rendite_quelle_pct")),
                                 ("Rating-Balance laut Quelle (USD)", entry.get("rating_balance_usd"))):
                numeric = _number(value)
                display = (f"{numeric:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                           if numeric is not None else "unbekannt")
                st.metric(label, display)
        st.caption("Renditezeitraum: " + _quellrendite_zeitraum(entry))
        st.caption("Finanzdatenstand laut Quelle: " + _finanzdatenstand(entry))
        st.caption("Quellenwerte gelesen am: " + str(entry.get("daten_gelesen_am") or "unbekannt")
                   + ". Dieser GET-Zeitpunkt belegt keine Frische der Finanzdaten.")
        if hint := _quellen_messhinweis(entry):
            st.caption(hint)
        return
    if entry.get("messhinweis"):
        st.caption(str(entry["messhinweis"]))
    if entry.get("ki_fehler"):
        st.warning(f"KI-Analyse unvollständig: {entry['ki_fehler']}")
    if entry.get("ki_hinweisstatus"):
        st.caption(str(entry["ki_hinweisstatus"]))
    short = entry.get("kurztest") if isinstance(entry.get("kurztest"), dict) else {}
    if short:
        st.write(f"Strategietyp: {short.get('strategietyp', 'nicht bestimmbar')} · "
                 f"Martingale: {short.get('martingale_einordnung', 'nicht beurteilbar')}")
        st.markdown(str(short.get("kurzurteil") or "Kein Kurzurteil vorhanden."))
        with st.expander("Belege, Risiken und Datenlücken des Kurztests"):
            st.json(short)
    else:
        st.caption("KI-Kurztest noch nicht vorhanden.")
    report = entry.get("bericht_markdown")
    if report:
        with st.expander("Ausführliche Top-5-Analyse", expanded=True):
            st.markdown(str(report))
            st.download_button("Bericht als Markdown", str(report).encode("utf-8"),
                               f"analyse-{entry.get('quelle')}-{entry.get('id')}.md",
                               "text/markdown", key=f"abonnenten_bericht_{token}")
    pdf = entry.get("pdf_path")
    if pdf and Path(pdf).is_file():
        with st.expander("PDF-Bericht"):
            data = Path(pdf).read_bytes()
            st.pdf(data, height=500, key=f"abonnenten_analyse_pdf_{token}")
            st.download_button("PDF herunterladen", data, Path(pdf).name, "application/pdf",
                               key=f"abonnenten_analyse_pdf_download_{token}")


@st.fragment(run_every=2.0)
def render_results() -> None:
    """Liest nur gespeicherte/aktuelle Zustände; Start nie aus einem Rerun."""
    if notice := st.session_state.pop("_abonnenten_analyse_notice", None):
        st.warning(notice)
    try:
        backend = _backend()
    except ModuleNotFoundError as exc:
        if exc.name != "mqlkiscanner.abonnenten_analyse":
            raise
        return
    try:
        runs = backend.laeufe()
        if not runs:
            return
        metadata = {str(r["id"]): r for r in runs}
        current = st.session_state.get("abonnenten_analyse_lauf")
        if current not in metadata:
            st.session_state["abonnenten_analyse_lauf"] = next(iter(metadata))
        st.subheader("Recherche: Diese Strategien genauer ansehen")
        run_id = st.selectbox("Analyseauftrag", list(metadata),
                             key="abonnenten_analyse_lauf",
                             format_func=lambda key: f"{metadata[key].get('created_at', key)} · "
                             f"{metadata[key].get('status', '')}")
        state = backend.zustand(run_id)
    except Exception as exc:
        st.error(f"Analysezustand nicht lesbar: {exc}")
        return
    st.caption(f"Ausgewählter Rechercheauftrag: {run_id} · "
               f"erstellt {metadata[run_id].get('created_at') or 'Zeitpunkt unbekannt'}")
    parallel = _parallelitaet_wert(state.get("ki_parallelitaet"))
    st.caption("KI-Parallelität dieses Auftrags: " + (
        f"bis zu {parallel} Kurzanalysen gleichzeitig." if parallel is not None
        else "nicht gespeichert (älterer Auftrag)."))
    if run_id != next(iter(metadata)):
        st.info("Sie sehen einen früheren Rechercheauftrag. Seine Fehler und Ergebnisse gehören "
                "zu diesem Auftrag. Ein neuerer Auftrag ist oben in der Auswahl verfügbar.")
    total, done = int(state.get("total") or 0), int(state.get("done") or 0)
    running = bool(state.get("laeuft"))
    ki_phase = _render_ki_fortschritt(state, backend, aktueller_lauf=run_id == next(iter(metadata)))
    st.caption(f"{state.get('status', '')} · {state.get('phase', '')} · "
               f"Anbieter-Endstände: {done}/{total}")
    if state.get("detail"):
        stamp = _meldungszeit(state)
        st.caption("Letzte gespeicherte Meldung" + (f" ({stamp})" if stamp else "")
                   + f": {state['detail']}")
    if state.get("updated_at"):
        st.caption(f"Auftrag zuletzt gespeichert: {state['updated_at']}")
    if not ki_phase:
        st.progress(min(1.0, max(0.0, done / total)) if total else 0.0)
    _render_quellenfortschritt(state, aktueller_lauf=run_id == next(iter(metadata)))
    if state.get("fehler"):
        st.warning(f"Fehler dieses Rechercheauftrags: {state['fehler']}")
    for source, snapshot in (state.get("snapshot_quellen") or {}).items():
        catalog = snapshot.get("abonnenten_katalog")
        if isinstance(catalog, dict) and catalog.get("complete") is False:
            st.warning(f"Quellenauswahl dieses Auftrags · {source}: " + _abo_auswahlhinweis({
                "abo_referenz_vollstaendig": False, "abo_ausgelassene_positionen": catalog.get("skipped_positions"),
                "abo_referenz_n": snapshot.get("anzahl")}))
        if snapshot.get("status") != "fertig":
            pending = snapshot.get("status") in {"wartet", "bereit", "laeuft", "gestartet"}
            message = (f"Quellenauswahl dieses Auftrags · {source}: "
                       f"{snapshot.get('grund') or 'noch nicht vollständig'}")
            (st.info if pending else st.warning)(message)
    with st.container(horizontal=True):
        if running:
            if st.button("Analyse stoppen", key=f"abonnenten_analyse_stop_{run_id}",
                         icon=":material/stop_circle:"):
                backend.stoppen(run_id)
                st.rerun()
        elif str(state.get("status", "")).casefold() not in {
                "fertig", "abgeschlossen", "completed", "complete", "done"}:
            if st.button("Analyse fortsetzen", key=f"abonnenten_analyse_resume_{run_id}",
                         icon=":material/play_arrow:"):
                try:
                    if backend.fortsetzen(run_id):
                        st.rerun()
                    else:
                        st.warning("Fortsetzen derzeit nicht möglich. Lauf-Lock und Voraussetzungen prüfen.")
                except Exception as exc:
                    st.error(f"Fortsetzen nicht möglich: {exc}")
    weight, limit = state.get("retdd_gewicht", 70), state.get("dd_grenze")
    st.caption(f"Jahres-RetDD-Gewicht: {weight} % · DD-Grenze: "
               + ("keine" if limit is None else f"{limit:g} %")
               + ". Diese Auswahlgewichte gelten für die RetDD-Kandidaten. "
               "Platzierungen bleiben während der Bearbeitung vorläufig.")
    entries = [_mit_abo_auswahl(entry, state) for entry in state.get("entries") or []]
    if entries:
        view = st.segmented_control("Ergebnisansicht", ["Kandidaten", "Quellenprofitabilität", "Alle", "Weitere Fälle"],
                                    default="Kandidaten", key=f"abonnenten_analyse_ansicht_{run_id}") or "Kandidaten"
        ranked = lambda e: e.get("rang") is not None and not _quellenprofitabilitaet(e)
        if view == "Kandidaten":
            visible = [e for e in entries if ranked(e)]
        elif view == "Quellenprofitabilität":
            visible = [e for e in entries if _quellenprofitabilitaet(e)]
        elif view == "Weitere Fälle":
            visible = [e for e in entries if not ranked(e) and not _quellenprofitabilitaet(e)]
        else:
            visible = entries
        if view == "Quellenprofitabilität":
            st.caption("Gewinn und Rendite sind Angaben der Quelle für den jeweils genannten Zeitraum. "
                       "Sie ersetzen keine Equity-Messung und ergeben keinen RetDD-Kandidatenrang. "
                       "Abrufzeitpunkt und Finanzdatenstand sind getrennt ausgewiesen.")
        else:
            st.caption("Jahres-RetDD aus kurzen Trade-Historien ist annualisiert; "
                       "H1 erfasst keine Intrabar-Tiefs. Quellrenditen werden nicht annualisiert.")
        df = ergebnis_tabelle(visible)
        if visible:
            signature = sha256(repr([e.get("signal_ref") for e in visible]).encode()).hexdigest()[:12]
            column_order = ["Rang", "Strategie", "Quelle", "Auswahlwert", "Jahres-RetDD",
                            "Equity-DD %", "Geom. %/Monat", "Monate", "Trades", "Abo-Perzentil",
                            "Strategietyp", "Prüfstatus", "KI-Kurzurteil"]
            if view == "Quellenprofitabilität":
                column_order = ["Strategie", "Quelle", "Quellengewinn USD", "Quellrendite %",
                                "Renditezeitraum (Quelle)", "Quellenprofitabilität",
                                "Finanzdatenstand (Quelle)", "Quellenwerte gelesen am", "Basisbewertung"]
            elif view != "Kandidaten":
                column_order.insert(-1, "Grund")
                if any(_quellenprofitabilitaet(e) for e in visible):
                    column_order[3:3] = ["Quellengewinn USD", "Quellrendite %", "Renditezeitraum (Quelle)",
                                         "Finanzdatenstand (Quelle)", "Quellenwerte gelesen am"]
            if any(entry.get("abo_referenz_vollstaendig") is False for entry in visible):
                column_order.append("Auswahlhinweis")
            selection = st.dataframe(
                df, hide_index=True, width="stretch", height=min(560, 40 + 35 * len(df)),
                column_order=column_order,
                key=f"abonnenten_analyse_tabelle_{run_id}_{view}_{signature}",
                selection_mode="single-row", on_select="rerun",
                column_config={"signal_ref": None,
                               "Jahres-RetDD": st.column_config.NumberColumn(format="%.2f"),
                               "Equity-DD %": st.column_config.NumberColumn(format="%.2f %%"),
                               "Auswahlwert": st.column_config.NumberColumn(format="%.2f"),
                               "Abo-Perzentil": st.column_config.NumberColumn(format="%.1f"),
                               "Geom. %/Monat": st.column_config.NumberColumn(format="%.2f %%"),
                               "Quellengewinn USD": st.column_config.NumberColumn(format="%.2f USD"),
                               "Quellrendite %": st.column_config.NumberColumn(format="%.2f %%"),
                               "Monate": st.column_config.NumberColumn(format="%.2f")})
            selected = getattr(getattr(selection, "selection", None), "rows", [])
            if selected and 0 <= selected[0] < len(visible):
                _render_detail(visible[selected[0]], str(run_id))
        else:
            st.info("Noch keine Ergebnisse in dieser Ansicht. Unter „Alle“ stehen Bearbeitungsstände und Gründe.")
        st.download_button("Gesamtes Analyseergebnis als CSV", ergebnis_csv(entries, state),
                           f"abonnenten-analyse-{run_id}.csv", "text/csv",
                           key=f"abonnenten_analyse_csv_{run_id}")
    if state.get("logs"):
        with st.expander("Analyseprotokoll"):
            st.code("\n".join(str(line) for line in state["logs"]), language=None)
