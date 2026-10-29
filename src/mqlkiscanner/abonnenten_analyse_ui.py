"""Dialog und Vergleich eines gespeicherten Abonnenten-Rechercheauftrags.

Nur ein bewusster Start/Fortsetzen löst Arbeit aus. Das Lesen von Fortschritt
und Ergebnissen startet keine Beschaffung, Berechnung oder Modellaufrufe.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from importlib import import_module
import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from . import config, db, quellen, scan_worker
from .llm import prompts

_ZUFLUSS_MODUS = "abo_zufluss_retdd_v1"


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

    entries = [_mit_abo_auswahl(entry, state) for entry in state.get("entries") or []]
    short = [entry for entry in entries if vorgesehen(entry)]
    top = [entry for entry in entries if _rang_sichtbar(entry)
           and (rank := _number(entry.get("rang"))) is not None and 1 <= rank <= 5]
    return {"kurz_fertig": sum(isinstance(entry.get("kurztest"), dict) and bool(entry["kurztest"])
                               for entry in short),
            "kurz_gesamt": len(short),
            "top5_fertig": sum(bool(str(entry.get("bericht_markdown") or "").strip()) for entry in top),
            "top5_gesamt": len(top),
            "endberichte_geprueft": sum(_endbericht_gueltig(entry) for entry in top),
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
        st.metric("Endberichte vollständig geprüft", f"{counts['endberichte_geprueft']}/{counts['top5_gesamt']}",
                  help="Abgeschlossene Endprüfung einschließlich angeforderter Berichtsredaktion. Vorhandener Text allein zählt nicht.")
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


def _policy_inputs(settings: dict, prefix: str, *, auswahl_modus: str | None = None) -> tuple[float, float | None]:
    weight, limit = _defaults(settings)
    if auswahl_modus == _ZUFLUSS_MODUS:
        weight = 30.0
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
    if auswahl_modus == _ZUFLUSS_MODUS:
        st.caption(f"Normierter Nettozuwachs 7 Tage {100 - retdd:g} % · Jahres-RetDD {retdd:g} %. "
                   "Normierung: Δ7 / durchschnittlicher Abonnentenbestand der ursprünglichen eingefrorenen "
                   "Top-200-Auswahl je Quelle; daraus ein gemeinsames Perzentil. "
                   "Das Quellenmittel ist kein plattformweiter Durchschnitt. Der aktuelle Bestand ist kein Zufluss.")
    else:
        st.caption(f"RetDD {retdd:g} % · relativer Abonnentenrang {100 - retdd:g} %. "
                   "Gewichtet werden Perzentile, keine absoluten Abonnentenzahlen.")
    return float(retdd), dd


def render_defaults_editor(settings: dict) -> None:
    """Eigener Speicherbereich, ohne andere Einstellungsgruppen zu überschreiben."""
    with st.expander("Standard für die Abonnentenanalyse", expanded=False):
        weight, limit = _policy_inputs(settings, "admin_abonnenten_analyse")
        parallel = _parallelitaet_input(settings, "admin_abonnenten_analyse")
        st.caption("Top 200 je Quelle, mindestens 1 Abonnent · 4 Wochen und 25 Trades (29.10.) · "
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
    label = st.selectbox("Auswahlbasis", ["Zufluss und RetDD", "Bestand und RetDD"],
                         key="abonnenten_analyse_auswahlbasis")
    mode = _ZUFLUSS_MODUS if label == "Zufluss und RetDD" else None
    if st.session_state.get("_abonnenten_analyse_letzter_modus", "unset") != mode:
        st.session_state["abonnenten_analyse_start_retdd"] = 30.0 if mode else _defaults(settings)[0]
        st.session_state["_abonnenten_analyse_letzter_modus"] = mode
    weight, limit = _policy_inputs(settings, "abonnenten_analyse_start", auswahl_modus=mode)
    parallel = _parallelitaet_input(settings, "abonnenten_analyse_start")
    st.info("Mindestens 4 Wochen und 25 abgeschlossene Trades (29.10.). Fehlende Daten werden automatisch geladen. "
            + ("Kurz-KI ist ein optionales Addon; die fünf Endanalysen benötigen vollständig geprüfte Daten "
               "und entschiedene Prüfhinweise. " if mode else
               "Kurz-KI für alle auswertbaren Strategien; ausführliche Analyse für die besten 5. ")
            + "Budget aus den Einstellungen.")
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
            mode_options = {"auswahl_modus": mode, "kurztest_optional": True,
                            "endpruefung_auto": True} if mode else {}
            run_id = backend.starten(chosen, settings={**settings, "abonnenten_analyse_parallelitaet": parallel},
                                     retdd_gewicht=weight, dd_grenze=limit, **mode_options)
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


def _rang_sichtbar(entry: dict) -> bool:
    pending = entry.get("review_pending") and (
        not entry.get("kurztest_optional") or _top5_hinweise(entry))
    return not (_quellenprofitabilitaet(entry) or pending
                or entry.get("ki_klaerung_gesperrt")
                or entry.get("ki_klaerung_status") == "nicht_beurteilbar"
                or entry.get("endpruefung_status") == "nicht_beurteilbar")


def _top5_hinweise(entry: dict) -> bool:
    decisions = entry.get("ki_pruefentscheidungen") or []

    def herkunft_liste(value):
        return [value] if isinstance(value, dict) else (
            [origin for origin in value if isinstance(origin, dict)] if isinstance(value, list) else [])

    def aktuelle_herkunft(origin):
        if origin.get("bericht_stufe") != "top5":
            return False
        return all(field not in entry or origin.get(origin_field) == entry[field]
                   for field, origin_field in (("top5_basis", "bericht_basis"),
                                                ("data_basis", "data_basis"),
                                                ("trades_sha256", "trades_sha256")))

    def entschieden(hint, origin=None):
        return any(isinstance(decision, dict) and decision.get("hinweis") == hint
                   and decision.get("entscheidung") in {"widerlegt", "bestaetigt", "nicht_beurteilbar"}
                   and bool(entry.get("ki_klaerung_basis"))
                   and decision.get("basis") == entry["ki_klaerung_basis"]
                   and any(aktuelle_herkunft(bound) and (origin is None or bound == origin)
                           for bound in herkunft_liste(decision.get("herkunft")))
                   for decision in decisions)

    report = entry.get("top5_befund")
    if isinstance(report, dict) and any(not entschieden(hint)
                                        for hint in report.get("neue_pruefhinweise") or []):
        return True
    return any(isinstance(record, dict) and origin.get("bericht_stufe") == "top5"
               and not entschieden(record.get("hinweis"), origin)
               for record in entry.get("ki_pruefhinweis_quellen") or []
               for origin in herkunft_liste(record.get("herkunft") if isinstance(record, dict) else None))


def _endpruefstatus(entry: dict) -> str:
    labels = {"wartet": "Vorläufig; Endprüfung wartet", "laeuft": "Vorläufig; Endprüfung läuft",
              "abgeschlossen": "Endprüfung abgeschlossen",
              "nicht_beurteilbar": "Endprüfung: nicht beurteilbar",
              "ki_fehler": "Vorläufig; Endprüfung mit Fehler"}
    if entry.get("endpruefung_status") == "abgeschlossen" and entry.get("review_pending"):
        return "Vorläufig; Endprüfung nach neuen Hinweisen erneut zu prüfen"
    if entry.get("endpruefung_status") == "abgeschlossen" and not _redaktion_geprueft(entry):
        return "Vorläufig; Berichtsredaktion noch nicht abgeschlossen"
    return labels.get(entry.get("endpruefung_status"),
                      "Vorläufig; Endprüfung offen" if entry.get("kurztest_optional") else "")


def _redaktion_geprueft(entry: dict, *, original: bool = False) -> bool:
    if not original and isinstance(entry.get("_bericht_redaktion_aktuell"), bool):
        return entry["_bericht_redaktion_aktuell"]
    if entry.get("bericht_redaktion_status") == "unbeurteilbar":
        return False
    if not entry.get("bericht_redaktion_verlangt"):
        return True
    try:
        reviewer = import_module("mqlkiscanner.abonnenten_analyse_redaktion")
    except ModuleNotFoundError:
        return False
    current_review = getattr(reviewer, "has_current_review", None)
    if not callable(current_review):
        return False
    try:
        return bool(current_review(entry))
    except (ValueError, TypeError, KeyError):
        return False


def _redaktionsstatus(entry: dict) -> str:
    status = entry.get("bericht_redaktion_status")
    if status == "geprueft":
        return ("Berichtsredaktion geprüft" if entry.get("bericht_redaktion_basis") and _redaktion_geprueft(entry)
                else "Berichtsredaktion nicht aktuell belegt; Bericht ist vorläufig")
    if status == "unbeurteilbar":
        return "Berichtsredaktion nicht beurteilbar; kein gültiger Endbericht"
    if entry.get("bericht_redaktion_verlangt"):
        return "Berichtsredaktion ausstehend; Bericht ist vorläufig"
    return ""


def _endbericht_gueltig(entry: dict) -> bool:
    return (not _quellenprofitabilitaet(entry) and entry.get("endpruefung_status") == "abgeschlossen"
            and bool(str(entry.get("bericht_markdown") or "").strip())
            and not entry.get("review_pending") and _rang_sichtbar(entry) and _redaktion_geprueft(entry))


def _ki_pruefstatus(entry: dict) -> str:
    if entry.get("review_pending"):
        if entry.get("kurztest_optional") and not _top5_hinweise(entry):
            return ("Kurz-KI: offene Addonhinweise; Kandidatenrang bleibt vorläufig"
                    if _rang_sichtbar(entry) else "Kurz-KI: offene Addonhinweise; Kandidatenrang gesperrt")
        return "Offene KI-Prüfung; kein Kandidatenrang"
    status = entry.get("ki_klaerung_status")
    if status == "nicht_beurteilbar":
        return "Prüfung beendet: nicht beurteilbar; Kandidatenrang gesperrt"
    if status == "geklaert":
        return ("Prüfung abgeschlossen; Kandidatenrang gesperrt"
                if entry.get("ki_klaerung_gesperrt") else "Prüfung abgeschlossen")
    if entry.get("ki_klaerung_gesperrt"):
        return "Kandidatenrang gesperrt; Prüfabschluss nicht belegt"
    return str(entry.get("ki_hinweisstatus") or "")


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _trend_frischehinweis(trend: dict) -> str:
    """Frische am gespeicherten Stichtag anzeigen, nicht aus der GET-Zeit erfinden."""
    parts = []
    age, distance = _number(trend.get("messalter_tage")), _number(trend.get("messabstand_7_tage"))
    if age is not None:
        parts.append(f"Alter des neuesten Messpunkts am Stichtag: {age:.2f} Tage")
    if distance is not None:
        parts.append(f"tatsächlicher Abstand der 7-Tage-Vergleichsmessungen: {distance:.2f} Tage")
    if trend.get("as_of"):
        parts.append(f"Stichtag: {trend['as_of']}")
    if trend.get("fetched_at"):
        parts.append(f"Historie gelesen: {trend['fetched_at']}")
    if trend.get("frischehinweis"):
        parts.append(str(trend["frischehinweis"]))
    if not parts:
        return "Messalter und Frische des Zuwachsfensters unbekannt."
    return "; ".join(parts) + ". GET-Zeit ist keine Messfrische."


def _nettogewinn_usd(entry: dict) -> float | None:
    if _quellenprofitabilitaet(entry):
        return None
    forensics = entry.get("forensik")
    stats = forensics.get("stats") if isinstance(forensics, dict) else None
    if not isinstance(stats, dict):
        return None
    currencies = {str(value).strip().upper() for value in (
        entry.get("account_currency"), stats.get("account_currency")) if value is not None and str(value).strip()}
    return _number(stats.get("net")) if currencies == {"USD"} else None


def _jahresrendite_hinweis(entry: dict) -> str:
    if _quellenprofitabilitaet(entry) or _number(entry.get("cagr_jahr_pct")) is None:
        return ""
    months = _number(entry.get("dauer_monate"))
    if months is not None and months < 12:
        return (f"Jahresrendite ist eine Hochrechnung aus {months:g} Monaten Exporthistorie; "
                "kein beobachtetes volles Jahresergebnis.")
    return ("Jahresrendite ist die annualisierte Rendite des Exportfensters."
            if months is not None else "Jahresrendite ist annualisiert; Dauer des Exportfensters unbekannt.")


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
    supplied = str(entry.get("abo_auswahl_hinweis") or "").strip()
    reference = _number(entry.get("abo_referenz_n"))
    basis = f"{int(reference)} erfassten Anbietern" if reference is not None and reference > 0 else "den erfassten Anbietern"
    return (f"Vorläufige Abonnentenauswahl: {skipped}" + (f"{supplied} " if supplied else "")
            + "Vollständige Top 200 nicht belegt. "
            f"Der Abonnentenrang gilt innerhalb von {basis}.")


def _mit_abo_auswahl(entry: dict, state: dict) -> dict:
    """Auch der eingefrorene Quellenbeleg bleibt in Ansicht/Export sichtbar."""
    entry = {**entry, "_bericht_redaktion_aktuell": _redaktion_geprueft(entry, original=True)}
    if state.get("kurztest_optional") is True:
        entry = {**entry, "kurztest_optional": True}
    return _daten_auswahlkopie(entry, state)


def _daten_auswahlkopie(entry: dict, state: dict) -> dict:
    """Auswahlbelege anzeigen, ohne Berichtsmodule oder neue Quellen zu lesen."""
    if state.get("auswahl_modus"):
        entry = {**entry, "auswahl_modus": state["auswahl_modus"]}
    snapshot = ((state.get("snapshot_quellen") or {}).get(entry.get("quelle")) or {})
    if snapshot.get("abonnenten_auswahl_unbestaetigt"):
        return {**entry, "abo_referenz_vollstaendig": False,
                "abo_auswahl_hinweis": snapshot.get("auswahl_hinweis") or "Auswahl/Abdeckung unbestätigt"}
    catalog = snapshot.get("abonnenten_katalog")
    if isinstance(catalog, dict) and catalog.get("complete") is False:
        return {**entry, "abo_referenz_vollstaendig": False,
                "abo_ausgelassene_positionen": catalog.get("skipped_positions", entry.get("abo_ausgelassene_positionen")),
                "abo_katalog_geprueft": catalog.get("scanned_providers", entry.get("abo_katalog_geprueft"))}
    if entry.get("auswahl_modus") == _ZUFLUSS_MODUS and not isinstance(entry.get("abo_referenz_vollstaendig"), bool):
        proof = snapshot.get("abonnenten_auswahl")
        confirmed = ((isinstance(proof, dict) and proof.get("verified") is True)
                     or (isinstance(catalog, dict) and catalog.get("complete") is True))
        return {**entry, "abo_referenz_vollstaendig": bool(confirmed),
                **({"abo_auswahl_hinweis": "Ursprüngliche Auswahl vorhanden; globale Top 200 unbestätigt, "
                     "ursprünglicher Auswahlbeleg fehlt."} if not confirmed else {})}
    return entry


def ergebnis_tabelle(entries: list[dict]) -> pd.DataFrame:
    """Eine Tabellenbasis für Anzeige und Export; unbekannte Zahlen bleiben leer."""
    rows = []
    for e in entries:
        source_values = _quellenprofitabilitaet(e)
        rank_visible = _rang_sichtbar(e)
        trend = e.get("abo_trend") if isinstance(e.get("abo_trend"), dict) else {}
        short = e.get("kurztest") if isinstance(e.get("kurztest"), dict) else {}
        rows.append({
            "Rang": e.get("rang") if rank_visible else None, "Strategie": e.get("name"),
            "Quelle": e.get("quelle"), "ID": e.get("id"),
            "Auswahlwert": e.get("auswahlwert") if rank_visible else None,
            "Jahres-RetDD": None if source_values else e.get("retdd_jahr"),
            "RetDD-Perzentil": e.get("retdd_perzentil") if rank_visible else None,
            "Equity-DD %": None if source_values else e.get("equity_dd_pct"),
            "Nettogewinn USD": _nettogewinn_usd(e),
            "Rendite Exportfenster %": _number(e.get("rendite_zeitraum_pct")) if not source_values else None,
            "Jahresrendite annualisiert %": _number(e.get("cagr_jahr_pct")) if not source_values else None,
            "Rendite-Hinweis": _jahresrendite_hinweis(e),
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
            "Nettozuwachs 7 Tage": _number(trend.get("delta_7")),
            "Nettozuwachs 7 Tage %": _number(trend.get("delta_7_pct")),
            "Zufluss-Perzentil": _number(e.get("abo_zufluss_perzentil")),
            "Zufluss / Quellenmittel": _number(e.get("abo_zufluss_skaliert")),
            "Quellenmittel Abonnenten": _number(e.get("abo_quellen_durchschnitt")),
            "Quellenmittel Anbieterzahl": _number(e.get("abo_quellen_referenz_n")),
            "Zufluss-Normierungsumfang": ("Ursprüngliche eingefrorene Top-200-Auswahl je Quelle"
                                         if e.get("auswahl_modus") == _ZUFLUSS_MODUS else ""),
            "Zufluss-Basiszeit": trend.get("basis_7_ts"),
            "Zufluss-Messzeit": trend.get("aktuell_ts"),
            "Zufluss-Frischehinweis": _trend_frischehinweis(trend) if trend else "",
            "Zufluss-Messalter Tage": _number(trend.get("messalter_tage")),
            "Zufluss-Messabstand Tage": _number(trend.get("messabstand_7_tage")),
            "Zufluss-Stichtag": trend.get("as_of"),
            "Zufluss-Historie gelesen am": trend.get("fetched_at"),
            "Zuflussbeleg geprüft": trend.get("verified") if isinstance(trend.get("verified"), bool) else None,
            "Auswahlbasis": ("Normierter 7-Tage-Nettozuwachs und RetDD" if e.get("auswahl_modus") == _ZUFLUSS_MODUS
                             else "Abonnentenbestand und RetDD"),
            "Abonnentenreferenz vollständig": (e.get("abo_referenz_vollstaendig")
                                                if isinstance(e.get("abo_referenz_vollstaendig"), bool) else None),
            "Ausgelassene API-Positionen": ", ".join(map(str, _abo_positionen(e))),
            "Geprüfte Kataloganbieter": e.get("abo_katalog_geprueft"),
            "Auswahlhinweis": _abo_auswahlhinweis(e),
            "Strategietyp": "" if source_values else short.get("strategietyp", ""),
            "Martingale": "" if source_values else short.get("martingale_einordnung", ""),
            "Prüfstatus": e.get("status", ""), "Grund": e.get("grund", ""),
            "KI-Prüfung": _ki_pruefstatus(e),
            "Endprüfung": _endpruefstatus(e),
            "Berichtsredaktion": _redaktionsstatus(e),
            "Endbericht geprüft": _endbericht_gueltig(e),
            "Kurz-KI optional": e.get("kurztest_optional") is True,
            "KI-Kandidatensperre": bool(e.get("ki_klaerung_gesperrt")),
            "KI-Kurzurteil": "" if source_values else short.get("kurzurteil", ""),
            "Vollbericht": "vorhanden" if e.get("bericht_markdown") and not source_values else "",
            "signal_ref": e.get("signal_ref", ""),
        })
    df = pd.DataFrame(rows)
    for column in ("Rang", "ID", "Auswahlwert", "Jahres-RetDD", "RetDD-Perzentil", "Equity-DD %",
                   "Nettogewinn USD", "Rendite Exportfenster %", "Jahresrendite annualisiert %",
                   "Geom. %/Monat", "Monate", "Trades", "Abonnenten", "Abo-Perzentil",
                   "Quellengewinn USD", "Quellrendite %", "Quellrendite Monate", "Rating-Balance USD",
                   "Geprüfte Kataloganbieter", "Nettozuwachs 7 Tage", "Nettozuwachs 7 Tage %", "Zufluss-Perzentil",
                   "Zufluss / Quellenmittel", "Quellenmittel Abonnenten", "Quellenmittel Anbieterzahl",
                   "Zufluss-Messalter Tage", "Zufluss-Messabstand Tage"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def ergebnis_csv(entries: list[dict], state: dict) -> bytes:
    entries = [_mit_abo_auswahl(entry, state) for entry in entries]
    df = ergebnis_tabelle(entries)
    for label, key in {
        "Messhinweis": "messhinweis", "Handel von": "zeit_von", "Handel bis": "zeit_bis",
        "Trade-SHA256": "trades_sha256", "Katalogstand": "katalog_stand",
        "Abo-Referenzanzahl": "abo_referenz_n", "KI-Fehler": "ki_fehler",
        "KI-Klärungsbasis": "ki_klaerung_basis",
        "Redaktionsbasis": "bericht_redaktion_basis",
        "Redaktion Berichts-SHA256": "bericht_redaktion_bericht_sha256",
        "Ursprünglicher Berichtsentwurf (Prüfgegenstand)": "bericht_markdown_original",
    }.items():
        df[label] = [entry.get(key) for entry in entries]
    df["KI-Hinweisstatus"] = [_ki_pruefstatus(entry) for entry in entries]
    df["KI-Prüfung offen"] = [bool(entry.get("review_pending")) for entry in entries]
    df["Endprüfhinweise offen"] = [bool(entry.get("review_pending")) and (
        not entry.get("kurztest_optional") or _top5_hinweise(entry)) for entry in entries]
    for label, key in {"Ursprüngliche KI-Prüfhinweise": "ki_pruefhinweise",
                       "KI-Prüfentscheidungen": "ki_pruefentscheidungen",
                       "Berichtskorrekturen (JSON)": "bericht_redaktion_korrekturen",
                       "Redaktionsprüfung (JSON)": "bericht_redaktion_result",
                       "Zufluss-Beleg (JSON)": "abo_trend"}.items():
        df[label] = [json.dumps(entry.get(key) or ({} if key in {"abo_trend", "bericht_redaktion_result"} else []),
                               ensure_ascii=False, allow_nan=False)
                     for entry in entries]
    df["Quellen-Messhinweis"] = [_quellen_messhinweis(entry) if _quellenprofitabilitaet(entry)
                                else "" for entry in entries]
    df["Lauf"] = state.get("id", "")
    df["Berichtsredaktion verlangt"] = [bool(entry.get("bericht_redaktion_verlangt")) for entry in entries]
    df["Geprüfter Endbericht (Markdown)"] = [str(entry.get("bericht_markdown") or "")
        if _endbericht_gueltig(entry) else "" for entry in entries]
    df["RetDD-Gewicht %"] = state.get("retdd_gewicht")
    inflow_mode = state.get("auswahl_modus") == _ZUFLUSS_MODUS
    popularity_weight = 100 - float(state.get("retdd_gewicht", 30 if inflow_mode else 70))
    df["Abonnenten-Gewicht %"] = None if inflow_mode else popularity_weight
    df["Zufluss-Gewicht %"] = popularity_weight if inflow_mode else None
    df["Auswahlmodus"] = state.get("auswahl_modus") or "abo_bestand_retdd_v1"
    df["DD-Grenze %"] = state.get("dd_grenze")
    df["Laufstatus"] = state.get("status", "")
    # Anbietertexte dürfen beim Öffnen in Excel keine Formeln ausführen.
    for name in df.select_dtypes(include=["object", "string"]).columns:
        df[name] = df[name].map(lambda value: "'" + value if isinstance(value, str)
                               and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def quellenabdeckung_tabelle(state: dict) -> pd.DataFrame:
    """Nur den eingefrorenen Auftrag zusammenfassen; keine Quelle neu prüfen."""
    entries = [_mit_abo_auswahl(entry, state) for entry in state.get("entries") or []]
    snapshots = state.get("snapshot_quellen") or {}
    sources = list(dict.fromkeys(state.get("quellen") or [
        *snapshots, *(str(entry.get("quelle") or "") for entry in entries)]))
    rows = []
    for source in sources:
        if not source:
            continue
        selected = [entry for entry in entries if entry.get("quelle") == source]
        measured = [entry for entry in selected if not _quellenprofitabilitaet(entry)]
        snapshot = snapshots.get(source) or {}
        problems = []
        if snapshot.get("status") != "fertig":
            problems.append("Quellensnapshot: " + str(snapshot.get("grund") or snapshot.get("status") or "unbekannt"))
        if snapshot.get("abonnenten_auswahl_unbestaetigt") or (
                isinstance(snapshot.get("abonnenten_katalog"), dict)
                and snapshot["abonnenten_katalog"].get("complete") is False) or any(
                    entry.get("abo_referenz_vollstaendig") is False for entry in selected):
            problems.append("Vollständige Top-200-Auswahl nicht belegt")
        gaps = [entry for entry in measured if not entry.get("data_done")]
        reasons = Counter(str(entry.get("grund") or "Datenversuch unvollständig") for entry in gaps)
        for reason, count in reasons.most_common(2):
            problems.append(f"{count} gespeicherte Datenlücken: {reason[:240]}")
        if len(reasons) > 2:
            problems.append(f"{len(reasons) - 2} weitere Datenlückengründe")

        def native_seven_days(entry):
            trend = entry.get("abo_trend")
            return (isinstance(trend, dict) and trend.get("verified") is True
                    and isinstance(trend.get("coverage"), dict) and trend["coverage"].get("7_tage") is True
                    and _number(trend.get("delta_7")) is not None)

        rows.append({
            "Quelle": source,
            "Eingefrorene Anbieter": len(selected),
            "RetDD-Daten vollständig": sum(bool(entry.get("data_done")) for entry in measured),
            "Für RetDD-Auswahl geeignet": sum(bool(entry.get("data_done")) and bool(entry.get("eligible"))
                and (retdd := _number(entry.get("retdd_jahr"))) is not None and retdd > 0
                and _rang_sichtbar(entry) for entry in measured),
            "Native 7-Tage-Trends": sum(native_seven_days(entry) for entry in selected),
            "Endberichte abgeschlossen": sum(_endbericht_gueltig(entry) for entry in measured),
            "Separate Quellenwerte": sum(_quellenprofitabilitaet(entry) for entry in selected),
            "Historischer Snapshotstand": snapshot.get("stand") or "unbekannt",
            "Historischer Quellenstatus": snapshot.get("status") or "unbekannt",
            "Historische offene Punkte": "; ".join(problems),
        })
    return pd.DataFrame(rows)


def _render_quellenabdeckung(state: dict) -> None:
    table = quellenabdeckung_tabelle(state)
    if table.empty:
        return
    with st.expander("Quellenabdeckung des ausgewählten Auftrags"):
        st.caption("Historischer Auftragsstand, kein aktueller Verbindungs- oder Loginstatus. "
                   "Gespeicherte Fehler und Datenlücken gehören zu diesem eingefrorenen Auftrag.")
        st.table(table)
        st.caption("Separate Quellenwerte, etwa Robo-Gewinnangaben, zählen nicht als vollständige RetDD-Daten. "
                   "RetDD-Eignung und native 7-Tage-Trends sind getrennte Voraussetzungen der Zuflussauswahl. "
                   "Endberichte zählen nur nach abgeschlossener Endprüfung; aus fehlenden Quellen folgt kein "
                   "vollständiger Vergleich aller Plattformen.")


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
    with st.container(horizontal=True):
        for label, value in (("Nettogewinn im Exportfenster (USD)", _nettogewinn_usd(entry)),
                             ("Rendite Exportfenster (%)", _number(entry.get("rendite_zeitraum_pct"))),
                             ("Jahresrendite annualisiert (%)", _number(entry.get("cagr_jahr_pct")))):
            display = (f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                       if value is not None else "unbekannt")
            st.metric(label, display)
    st.caption("Nettogewinn stammt aus dem vorhandenen Trade-Export und wird nur bei belegter USD-Kontowährung "
               "als USD gezeigt. Rendite und annualisierte Jahresrendite verwenden die gespeicherte Kapitalflussbasis.")
    if entry.get("zeit_von") or entry.get("zeit_bis"):
        st.caption(f"Exportfenster: {entry.get('zeit_von') or 'Beginn unbekannt'} bis "
                   f"{entry.get('zeit_bis') or 'Ende unbekannt'}")
    if hint := _jahresrendite_hinweis(entry):
        st.caption(hint)
    trend = entry.get("abo_trend")
    if isinstance(trend, dict):
        delta = _number(trend.get("delta_7"))
        st.metric("Netto-Bestandsänderung in 7 Tagen", f"{delta:+g}" if delta is not None else "unbekannt")
        percent = _number(trend.get("delta_7_pct"))
        if percent is not None:
            st.caption(f"Relative Bestandsänderung: {percent:+g} %")
        st.caption(f"Vergleichsmessung: {trend.get('basis_7_ts') or 'unbekannt'} · "
                   f"neuester Messpunkt: {trend.get('aktuell_ts') or 'unbekannt'}")
        st.caption(_trend_frischehinweis(trend))
        if trend.get("verified") is not True:
            st.warning("Kein geprüfter 7-Tage-Zuflussbeleg. Der aktuelle Abonnentenbestand ersetzt diesen Beleg nicht.")
        st.caption("Nettozuwachs ist die Differenz zweier Bestände; einzelne Zu- und Abgänge werden damit nicht beobachtet.")
    if entry.get("auswahl_modus") == _ZUFLUSS_MODUS:
        mean, size = _number(entry.get("abo_quellen_durchschnitt")), _number(entry.get("abo_quellen_referenz_n"))
        scaled = _number(entry.get("abo_zufluss_skaliert"))
        st.metric("Nettozuwachs / Quellenmittel", f"{scaled:.4f}" if scaled is not None else "unbekannt")
        st.caption("Normierungsbasis: durchschnittlicher positiver Abonnentenbestand der ursprünglichen "
                   f"eingefrorenen Top-200-Auswahl der Quelle {entry.get('quelle') or 'unbekannt'}; "
                   + (f"{mean:g} Abonnenten bei {int(size)} Anbietern" if mean is not None and size is not None
                      else "Mittelwert oder Anbieterzahl unbekannt")
                   + f". Auswahlstand: {entry.get('katalog_stand') or 'unbekannt'}. "
                   "Das ist kein Mittelwert der gesamten Plattform. Das Zufluss-Perzentil vergleicht die "
                   "normierten Werte gemeinsam über die Quellen.")
    if entry.get("ki_fehler"):
        st.warning(f"KI-Analyse unvollständig: {entry['ki_fehler']}")
    if status := _endpruefstatus(entry):
        st.caption(status)
    if status := _ki_pruefstatus(entry):
        (st.warning if entry.get("review_pending") or entry.get("ki_klaerung_gesperrt")
         else st.caption)(status)
    if entry.get("ki_klaerung_gesperrt"):
        st.caption("Die Kandidatensperre ist keine automatische Bestätigung von Martingale "
                   "und ändert die bestehende Workflow-Ampel nicht.")
    decisions = entry.get("ki_pruefentscheidungen")
    if isinstance(decisions, list) and decisions:
        with st.expander("Entscheidungen zu KI-Prüfhinweisen"):
            labels = {"widerlegt": "Widerlegt", "bestaetigt": "Bestätigt",
                      "nicht_beurteilbar": "Nicht beurteilbar"}
            for decision in decisions:
                if not isinstance(decision, dict):
                    continue
                st.markdown("**" + labels.get(decision.get("entscheidung"), "Entscheidung unbekannt") + "**")
                effects = {"keine_sperre": "Keine Kandidatensperre",
                           "dokumentierter_risikohinweis": "Dokumentierter Risikohinweis; keine zusätzliche Kandidatensperre",
                           "bewertungsgrundlage_unzureichend": "Bewertungsgrundlage unzureichend; Kandidatenrang gesperrt"}
                if decision.get("auswirkung") in effects:
                    st.caption(effects[decision["auswirkung"]])
                st.write(str(decision.get("begruendung") or "Begründung nicht vorhanden"))
            st.json({"entscheidungen": decisions,
                     "urspruengliche_pruefhinweise": entry.get("ki_pruefhinweise") or [],
                     "klaerungsbasis": entry.get("ki_klaerung_basis")})
    if status := _redaktionsstatus(entry):
        (st.caption if _redaktion_geprueft(entry) else st.warning)(status)
    corrections = entry.get("bericht_redaktion_korrekturen")
    if isinstance(corrections, list) and corrections:
        with st.expander("Nachvollziehbare Berichtskorrekturen"):
            st.caption("Alte Textstellen sind Prüfgegenstand; maßgeblich ist der geprüfte korrigierte Bericht.")
            st.json({"korrekturen": corrections, "redaktionsbasis": entry.get("bericht_redaktion_basis"),
                     "bericht_sha256": entry.get("bericht_redaktion_bericht_sha256"),
                     "redaktionspruefung": entry.get("bericht_redaktion_result")})
    original_report = entry.get("bericht_markdown_original")
    if original_report:
        with st.expander("Ursprünglicher Berichtsentwurf als Prüfgegenstand"):
            st.code(str(original_report), language="markdown")
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
        provisional = not _redaktion_geprueft(entry)
        with st.expander("Vorläufiger Berichtsentwurf; Redaktion offen" if provisional
                         else "Ausführliche Top-5-Analyse", expanded=not provisional):
            st.markdown(str(report))
            st.download_button("Berichtsentwurf als Markdown" if provisional else "Bericht als Markdown", str(report).encode("utf-8"),
                               f"analyse-{entry.get('quelle')}-{entry.get('id')}.md",
                               "text/markdown", key=f"abonnenten_bericht_{token}")
    pdf = entry.get("pdf_path")
    if pdf and Path(pdf).is_file():
        with st.expander("Vorläufiges PDF; Berichtsredaktion offen" if not _redaktion_geprueft(entry) else "PDF-Bericht"):
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
        if snapshot.get("abonnenten_auswahl_unbestaetigt"):
            st.warning(f"Quellenauswahl dieses Auftrags · {source}: " + _abo_auswahlhinweis({
                "abo_referenz_vollstaendig": False, "abo_auswahl_hinweis": snapshot.get("auswahl_hinweis"),
                "abo_referenz_n": snapshot.get("anzahl")}))
        elif isinstance(catalog, dict) and catalog.get("complete") is False:
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
    inflow_mode = state.get("auswahl_modus") == _ZUFLUSS_MODUS
    weight, limit = state.get("retdd_gewicht", 30 if inflow_mode else 70), state.get("dd_grenze")
    st.caption((f"Gewicht normierter Nettozuwachs (7 Tage): {100 - float(weight):g} % · " if inflow_mode else "")
               + f"Jahres-RetDD-Gewicht: {weight} % · DD-Grenze: "
               + ("keine" if limit is None else f"{limit:g} %")
               + ". Diese Auswahlgewichte gelten für die RetDD-Kandidaten. "
               "Platzierungen bleiben während der Bearbeitung vorläufig.")
    if inflow_mode:
        st.caption("Zufluss: Δ7 geteilt durch den durchschnittlichen Abonnentenbestand der ursprünglichen "
                   "eingefrorenen Top-200-Auswahl je Quelle; gewichtet wird das gemeinsame Perzentil dieser Werte. "
                   "Der Durchschnitt umfasst die gespeicherte Auswahl mit positivem Bestand und ist kein "
                   "Plattformmittel. Bestand, Normierungsbasis, Vergleichszeitpunkte und Frische bleiben getrennt sichtbar.")
    entries = [_mit_abo_auswahl(entry, state) for entry in state.get("entries") or []]
    _render_quellenabdeckung(state)
    if entries:
        if any(e.get("review_pending") or e.get("ki_pruefentscheidungen")
               or e.get("ki_klaerung_gesperrt") for e in entries):
            if state.get("kurztest_optional") is True:
                st.caption("KI-Prüfhinweise: "
                           f"{sum(bool(e.get('review_pending')) and _top5_hinweise(e) for e in entries)} offene Endprüfungen · "
                           f"{sum(bool(e.get('review_pending')) and not _top5_hinweise(e) for e in entries)} offene Addonfälle · "
                           f"{sum(bool(e.get('ki_klaerung_gesperrt')) for e in entries)} mit Kandidatensperre. "
                           "Kurz-KI ist optional; Datenlücken bleiben gesondert ausgewiesen.")
            else:
                st.caption("KI-Prüfungen: "
                           f"{sum(bool(e.get('review_pending')) for e in entries)} offen · "
                           f"{sum(not e.get('review_pending') and e.get('ki_klaerung_status') in {'geklaert', 'nicht_beurteilbar'} for e in entries)} beendet · "
                           f"{sum(bool(e.get('ki_klaerung_gesperrt')) for e in entries)} mit Kandidatensperre. "
                           "Datenlücken bleiben gesondert ausgewiesen.")
        if state.get("kurztest_optional") is True:
            st.caption("Kandidatenränge bleiben vorläufig, bis die jeweilige Endprüfung abgeschlossen ist. "
                       "Fehlende Kurztests und reine Addonhinweise blockieren den Workflow nicht.")
        view = st.segmented_control("Ergebnisansicht", ["Kandidaten", "Quellenprofitabilität", "Alle", "Weitere Fälle"],
                                    default="Kandidaten", key=f"abonnenten_analyse_ansicht_{run_id}") or "Kandidaten"
        ranked = lambda e: e.get("rang") is not None and _rang_sichtbar(e)
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
                            "Equity-DD %", "Nettogewinn USD", "Rendite Exportfenster %",
                            "Geom. %/Monat", "Monate", "Trades", "Abo-Perzentil",
                            "Strategietyp", "Prüfstatus", "KI-Prüfung", "Endprüfung", "Berichtsredaktion", "KI-Kurzurteil"]
            if inflow_mode:
                column_order[column_order.index("Abo-Perzentil")] = "Zufluss-Perzentil"
                column_order[3:3] = ["Nettozuwachs 7 Tage", "Zufluss / Quellenmittel", "Nettozuwachs 7 Tage %"]
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
                df, hide_index=True, placeholder="", width="stretch", height=min(560, 40 + 35 * len(df)),
                column_order=column_order,
                key=f"abonnenten_analyse_tabelle_{run_id}_{view}_{signature}",
                selection_mode="single-row", on_select="rerun",
                column_config={"signal_ref": None,
                               "Jahres-RetDD": st.column_config.NumberColumn(format="%.2f"),
                               "Equity-DD %": st.column_config.NumberColumn(format="%.2f %%"),
                               "Nettogewinn USD": st.column_config.NumberColumn(format="%.2f USD"),
                               "Rendite Exportfenster %": st.column_config.NumberColumn(format="%.2f %%"),
                               "Auswahlwert": st.column_config.NumberColumn(format="%.2f"),
                               "Abo-Perzentil": st.column_config.NumberColumn(format="%.1f"),
                               "Zufluss-Perzentil": st.column_config.NumberColumn(format="%.1f"),
                               "Zufluss / Quellenmittel": st.column_config.NumberColumn(format="%.4f"),
                               "Nettozuwachs 7 Tage": st.column_config.NumberColumn(format="%+.0f"),
                               "Nettozuwachs 7 Tage %": st.column_config.NumberColumn(format="%+.1f %%"),
                               "Geom. %/Monat": st.column_config.NumberColumn(format="%.2f %%"),
                               "Quellengewinn USD": st.column_config.NumberColumn(format="%.2f USD"),
                               "Quellrendite %": st.column_config.NumberColumn(format="%.2f %%"),
                               "Monate": st.column_config.NumberColumn(format="%.2f")})
            selected = getattr(getattr(selection, "selection", None), "rows", [])
            if selected and 0 <= selected[0] < len(visible):
                _render_detail(visible[selected[0]], str(run_id))
        else:
            st.info("Noch keine Ergebnisse in dieser Ansicht. Unter „Alle“ stehen Bearbeitungsstände und Gründe.")
        st.download_button("Gesamtes Analyseergebnis als CSV", ergebnis_csv(state.get("entries") or [], state),
                           f"abonnenten-analyse-{run_id}.csv", "text/csv",
                           key=f"abonnenten_analyse_csv_{run_id}")
    if state.get("logs"):
        with st.expander("Analyseprotokoll"):
            st.code("\n".join(str(line) for line in state["logs"]), language=None)


# Aktuelle Stufe 1: Die historischen Berichtsansichten oben werden von der
# Abonnentenstatistik nicht mehr aufgerufen. Gespeicherte Artefakte bleiben erhalten.
_DATEN_MODUS = "daten_ohne_ki_v1"


def _daten_trade_anzahl(entry: dict) -> float | None:
    trades = _number(entry.get("trades"))
    if trades is None or trades < 0:
        return None
    if trades == 0 and not (entry.get("trades_path") or entry.get("data_done")
                            or entry.get("trade_history_complete") is True):
        return None
    return trades


def _daten_trade_status(entry: dict) -> str:
    if _quellenprofitabilitaet(entry):
        return "Quellenwerte; kein eigener Trade-Export"
    complete = entry.get("trade_history_complete")
    return ("Vollständigkeit des gelieferten Exportfensters belegt" if complete is True
            else "Quelle meldet eine Teillieferung" if complete is False
            else "Vollständigkeit des gelieferten Exportfensters nicht belegt")


def _modell_details_text(value, prefix="") -> str:
    """Parameter lesbar exportieren, ohne ein JSON-Artefakt in die CSV einzubauen."""
    if isinstance(value, dict):
        return "; ".join(_modell_details_text(child, f"{prefix}.{key}" if prefix else str(key))
                         for key, child in value.items())
    if isinstance(value, list):
        return "; ".join(_modell_details_text(child, f"{prefix}[{index}]") for index, child in enumerate(value))
    display = "unbekannt" if value is None else "ja" if value is True else "nein" if value is False else str(value)
    return f"{prefix}: {display}" if prefix else display


def _modell_kapitalfluss_anzahl(model: dict) -> float | None:
    value = model.get("ignorierte_kapitalfluesse")
    return _number(value.get("anzahl") if isinstance(value, dict) else value)


def _modell_spalten(entry: dict) -> dict:
    model = entry.get("modell") if isinstance(entry.get("modell"), dict) else {}
    flows = model.get("ignorierte_kapitalfluesse")
    flows = flows if isinstance(flows, dict) else {}
    native = entry.get("native_cache_import") or {}
    reason = str(model.get("grund") or "")
    if native.get("status") in {"datenluecke", "ausgenommen"} and native.get("grund"):
        reason = (reason + " Lokaler Tradebestand: " + str(native["grund"])).strip()
    return {
        "Modell-Startkapital USD": _number(model.get("startkapital_usd")),
        "Modell-Kapitalbasis/Herkunft": str(model.get("kapital_methode") or ""),
        "Modell-Kapitalhinweis": str(model.get("kapital_hinweis") or ""),
        "Modell-Kapitaldetails": _modell_details_text(model.get("kapital_details") or {}),
        "Modell-Nettogewinn USD": _number(model.get("nettogewinn_usd")),
        "Modell-Rendite Exportfenster %": _number(model.get("rendite_zeitraum_pct")),
        "Modell-Jahresrendite annualisiert %": _number(model.get("cagr_jahr_pct")),
        "Modell-Equity-DD inkl. Floating %": _number(model.get("equity_dd_pct")),
        "Modell-Equity-DD USD": _number(model.get("equity_dd_usd")),
        "Modell-Jahres-RetDD": _number(model.get("retdd_jahr")),
        "Modell-Closing-DD %": _number(model.get("closing_dd_pct")),
        "Modell-Closing-DD USD": _number(model.get("closing_dd_usd")),
        "Modell-Währung": model.get("waehrung"),
        "Modell-Trades": _number(model.get("trade_anzahl")),
        "Modell-Handel von": model.get("zeit_von"), "Modell-Handel bis": model.get("zeit_bis"),
        "Modell-H1-Abdeckung %": _number(model.get("h1_abdeckung_pct")),
        "Modell-Kapitalflussannahme": model.get("annahme_kapitalfluesse"),
        "Modell-Annahmehinweis": ("Szenario ohne Ein-/Auszahlungen; Jahreswerte sind annualisierte Modellwerte, "
                                  "keine beobachteten Kontowerte." if model else ""),
        "Im Modell ignorierte Kapitalflüsse": _modell_kapitalfluss_anzahl(model),
        "Ignorierte Einzahlungen (nativ)": _number(flows.get("einzahlungen_nativ")),
        "Ignorierte Auszahlungen (nativ)": _number(flows.get("auszahlungen_nativ")),
        "Währung ignorierter Kapitalflüsse": flows.get("waehrung"),
        "Modellstatus": str(model.get("status") or "nicht berechnet"),
        "Modellgrund": reason,
        "Lokaler Tradeimport-Status": str(native.get("status") or "nicht geprüft"),
        "Lokaler Tradeimport-Hinweis": str(native.get("grund") or ""),
        "Modell-Trade-SHA256": model.get("trade_sha256"),
        "Modell berechnet am": model.get("berechnet_am"), "Modellversion": model.get("version"),
    }


def daten_tabelle(entries: list[dict], state: dict | None = None) -> pd.DataFrame:
    """Reine Messwerttabelle; jede ausgewählte Identität bleibt sichtbar."""
    state = {**(state or {}), "auswahl_modus": _ZUFLUSS_MODUS}
    rows = []
    for raw in entries:
        e = _daten_auswahlkopie(raw, state)
        source_values = _quellenprofitabilitaet(e)
        trend = e.get("abo_trend") if isinstance(e.get("abo_trend"), dict) else {}
        equity = e.get("equity") if isinstance(e.get("equity"), dict) else {}
        status = ("Quellenwerte" if source_values else "Berechnet" if e.get("data_done")
                  else "Wird berechnet" if e.get("status") == "rechnet" else "Datenlücke")
        coverage = _number(equity.get("abdeckung_pct_raw", equity.get("abdeckung_pct")))
        coverage_text = ("Quellenwerte; keine eigene Equity-Messung" if source_values
                         else (f"H1-Raster {coverage:.2f} %" if coverage is not None
                               else "H1-Abdeckung unbekannt"))
        rows.append({
            "Quelle": e.get("quelle"), "Strategie": e.get("name"), "ID": e.get("id"),
            "Link": quellen.oeffnen_url(e.get("quelle"), e.get("id"), e.get("url") or ""),
            "Abonnenten": _number(e.get("abonnenten")),
            "Nettozuwachs 7 Tage": _number(trend.get("delta_7")),
            "Zufluss / Quellenmittel": _number(e.get("abo_zufluss_skaliert")),
            "Nettogewinn USD": _nettogewinn_usd(e),
            "Rendite Exportfenster %": None if source_values else _number(e.get("rendite_zeitraum_pct")),
            "Max. gemessener Equity-DD %": None if source_values else _number(e.get("equity_dd_pct")),
            "Jahres-RetDD": None if source_values else _number(e.get("retdd_jahr")),
            "RetDD-Status": "keine eigene Messung" if source_values else str(e.get("retdd_status") or "nicht separat belegt"),
            "RetDD-Hinweis": "" if source_values else str(e.get("retdd_grund") or ""),
            "Monate": _number(e.get("dauer_monate")), "Trades": _daten_trade_anzahl(e),
            "Abdeckungsstatus": coverage_text, "Status": status, "Grund": str(e.get("grund") or ""),
            "Trade-Export-Status": _daten_trade_status(e),
            "Trade-Export-Hinweis": str(e.get("trade_history_reason") or ""),
            "Währung Trade-Export": e.get("trade_money_currency"),
            "Nettogewinn Kontowährung": _number(e.get("netto_quellwaehrung")) if not source_values else None,
            "Datenrang": None if source_values else _number(e.get("rang")),
            "Vorauswertung": None if source_values else _number(e.get("auswahlwert")),
            "Quellengewinn USD": _number(e.get("gewinn_usd")) if source_values else None,
            "Quellrendite %": _number(e.get("rendite_quelle_pct")) if source_values else None,
            "Renditezeitraum (Quelle)": _quellrendite_zeitraum(e) if source_values else "",
            "Finanzdatenstand (Quelle)": _finanzdatenstand(e) if source_values else "",
            "Nettozuwachs 7 Tage %": _number(trend.get("delta_7_pct")),
            "Quellenmittel Abonnenten": _number(e.get("abo_quellen_durchschnitt")),
            "Quellenmittel Anbieterzahl": _number(e.get("abo_quellen_referenz_n")),
            "Zufluss-Perzentil": _number(e.get("abo_zufluss_perzentil")),
            "Vergleichsmessung": trend.get("basis_7_ts"), "Neueste Abomessung": trend.get("aktuell_ts"),
            "Zufluss-Frischehinweis": _trend_frischehinweis(trend) if trend else "",
            "Handel von": e.get("zeit_von"), "Handel bis": e.get("zeit_bis"),
            "Jahresrendite annualisiert %": None if source_values else _number(e.get("cagr_jahr_pct")),
            "Rendite-Hinweis": _jahresrendite_hinweis(e),
            "H1-Abdeckung %": coverage, "Trade-SHA256": e.get("trades_sha256"),
            "Auswahlstand": e.get("katalog_stand"), "Auswahlhinweis": _abo_auswahlhinweis(e),
            "Messbasis": ("Ausgewiesene Quellenwerte" if source_values
                          else "Exportierte geschlossene Positionen; Floating an H1-Bar-Schlüssen"),
            **_modell_spalten(e),
        })
    df = pd.DataFrame(rows)
    # Nur Messwerte typisieren, auch wenn die ganze Spalte unbekannt ist.
    # Namen, Identitäten, Versionen und Hashes bleiben unverändert als Text;
    # die leere Darstellung fehlender Werte steuert st.dataframe.placeholder.
    for spalte in (
        "Abonnenten", "Nettozuwachs 7 Tage", "Zufluss / Quellenmittel", "Nettogewinn USD",
        "Rendite Exportfenster %", "Max. gemessener Equity-DD %", "Jahres-RetDD", "Monate", "Trades",
        "Nettogewinn Kontowährung", "Datenrang", "Vorauswertung", "Quellengewinn USD", "Quellrendite %",
        "Nettozuwachs 7 Tage %", "Quellenmittel Abonnenten", "Quellenmittel Anbieterzahl", "Zufluss-Perzentil",
        "Jahresrendite annualisiert %", "H1-Abdeckung %", "Modell-Startkapital USD", "Modell-Nettogewinn USD",
        "Modell-Rendite Exportfenster %", "Modell-Jahresrendite annualisiert %",
        "Modell-Equity-DD inkl. Floating %", "Modell-Equity-DD USD", "Modell-Jahres-RetDD",
        "Modell-Closing-DD %", "Modell-Closing-DD USD", "Modell-Trades", "Modell-H1-Abdeckung %",
        "Im Modell ignorierte Kapitalflüsse", "Ignorierte Einzahlungen (nativ)", "Ignorierte Auszahlungen (nativ)",
    ):
        if spalte in df:
            df[spalte] = pd.to_numeric(df[spalte], errors="coerce")
    return df


def daten_csv(entries: list[dict], state: dict | None = None) -> bytes:
    table = daten_tabelle(entries, state)
    for name in table.select_dtypes(include=["object", "string"]).columns:
        table[name] = table[name].map(lambda value: "'" + value if isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    return table.to_csv(index=False, sep=";").encode("utf-8-sig")


def daten_quellenabdeckung(state: dict) -> pd.DataFrame:
    rows = []
    entries = state.get("entries") or []
    snapshots = state.get("snapshot_quellen") or {}
    sources = list(dict.fromkeys(state.get("quellen") or [*snapshots, *(e.get("quelle") for e in entries)]))
    for source in sources:
        selected = [e for e in entries if e.get("quelle") == source]
        measured = [e for e in selected if not _quellenprofitabilitaet(e)]
        snapshot = snapshots.get(source) or {}
        missing = [e for e in measured if not e.get("data_done")]
        reasons = Counter(str(e.get("grund") or "Trade-/Kapital-/Kursgrundlage unvollständig") for e in missing)
        models = [e["modell"] for e in selected if isinstance(e.get("modell"), dict)]
        model_counts = ({"Modell-Startkapital vorhanden": sum((_number(model.get("startkapital_usd")) or 0) > 0 for model in models),
                         "Modell-DD berechnet": sum(_number(model.get("equity_dd_pct")) is not None for model in models),
                         "Modell-RetDD berechnet": sum(_number(model.get("retdd_jahr")) is not None for model in models),
                         "Offene Modellpunkte": sum(model.get("status") != "berechnet" for model in models)} if models else {})
        rows.append({"Quelle": source, "Ausgewählte Anbieter": len(selected),
            "Exportdaten berechnet": sum(bool(e.get("data_done")) for e in measured),
            "DD und RetDD berechenbar": sum(_number(e.get("retdd_jahr")) is not None
                and _number(e.get("equity_dd_pct")) is not None for e in measured),
            "Native 7-Tage-Trends": sum(isinstance(e.get("abo_trend"), dict)
                and e["abo_trend"].get("verified") is True for e in selected),
            "Separate Quellenwerte": sum(_quellenprofitabilitaet(e) for e in selected),
            **model_counts,
            "Datenlücken": len(missing), "Historischer Auswahlstand": snapshot.get("stand") or "unbekannt",
            "Gespeicherte offene Datenpunkte": "; ".join(
                ([str(snapshot["grund"])] if snapshot.get("grund") else [])
                + [f"{n}× {reason[:200]}" for reason, n in reasons.most_common(2)])})
    return pd.DataFrame(rows)


def _render_daten_detail(entry: dict, state: dict) -> None:
    table = daten_tabelle([entry], state)
    st.markdown(f"**{entry.get('name') or 'Strategie'}** · {entry.get('quelle')}:{entry.get('id')}")
    model = entry.get("modell")
    if isinstance(model, dict):
        st.info("Modellszenario: Startkapital und davon abhängige DD-/Rendite-/RetDD-Werte sind Modellwerte. "
                "Die echten gespeicherten Messungen stehen getrennt in der Tabelle und im Export.")
        st.caption(str(model.get("kapital_methode") or "Kapitalherkunft nicht angegeben")
                   + ": " + str(model.get("kapital_hinweis") or ""))
        if model.get("annahme_kapitalfluesse") == "keine":
            count = _modell_kapitalfluss_anzahl(model)
            st.caption("Modellannahme: keine Ein- oder Auszahlungen. Bekannte Kapitalflussereignisse werden ignoriert: "
                       + (f"{int(count)}" if count is not None else "Anzahl unbekannt") + ".")
        if isinstance(model.get("kapital_details"), dict):
            with st.expander("Parameter der Modell-Kapitalbasis"):
                st.json(model["kapital_details"])
    # Link ist in der Haupttabelle klickbar; im Messwert-Dump wäre er nur Text.
    values = (table.iloc[0].drop(labels=["Link"], errors="ignore")
              .map(lambda value: "unbekannt" if pd.isna(value) else str(value)))
    st.table(values.rename_axis("Messwert").reset_index(name="Wert"))
    if hint := _abo_auswahlhinweis(_daten_auswahlkopie(entry, {**state, "auswahl_modus": _ZUFLUSS_MODUS})):
        st.warning(hint)
    with st.expander("Gespeicherter Trade-Export"):
        st.caption(_daten_trade_status(entry))
        count = _daten_trade_anzahl(entry)
        st.caption("Exportierte abgeschlossene Trades: " + (f"{int(count)}" if count is not None else "unbekannt")
                   + ". Aktuell offene Positionen werden damit nicht als erfasst behauptet.")
        path, expected = entry.get("trades_path"), entry.get("trades_sha256")
        if not path or not expected:
            st.caption("Kein gespeicherter Trade-Export mit SHA-Beleg vorhanden.")
        else:
            try:
                db.verify_trade_file(path, expected)
                data = Path(path).read_bytes()
                if sha256(data).hexdigest() != expected:
                    raise ValueError("Trade-Export während des Lesens verändert")
                identity = f"{state.get('id')}:{entry.get('signal_ref')}:{expected}"
                st.download_button("Gespeicherten Trade-Export herunterladen", data,
                    f"trades-{entry.get('quelle')}-{entry.get('id')}.csv", "text/csv",
                    key="abonnenten_daten_trades_" + sha256(identity.encode()).hexdigest()[:16])
                st.caption("SHA256: " + str(expected))
            except (OSError, ValueError, TypeError) as error:
                st.warning(f"Gespeicherter Trade-Export nicht belegt: {error}")


@st.dialog("Daten sammeln und Kennzahlen berechnen", width="medium")
def daten_dialog() -> None:
    sources = db.list_quellen(nur_aktiv=True)
    labels = {str(source["kuerzel"]): quellen.anzeige_name(source) for source in sources}
    if not labels:
        st.warning("Keine aktive Datenquelle konfiguriert.")
        return
    chosen = st.multiselect("Quellen", list(labels), default=list(labels),
                            format_func=lambda key: labels[key], key="abonnenten_daten_quellen")
    st.caption("Je Quelle bis zu 200 ausgewählte Anbieter mit mindestens einem Abonnenten; MQL4/5 gemeinsam. "
               "Alle verfügbaren Trades des Exportfensters werden für die Messung verwendet.")
    st.info("Stufe 1 sammelt Daten und berechnet Zufluss, Nettogewinn, Rendite, Floating-Equity-DD und RetDD. "
            "Alle ausgewählten Anbieter bleiben mit Datenstatus und offenen Datenpunkten in der Tabelle.")
    # Frische-Schranke (Nutzer-Anforderung 25.10.: Abonnentenzahlen maximal
    # 24 h alt, sonst erst 'Abonnentenzahlen aktualisieren' mit 'Frisch
    # messen'). Geprüft wird die jüngste echte MESSUNG je gewählter Quelle.
    veraltet: dict[str, float] = {}
    if chosen:
        try:
            from . import abonnenten_statistik
            frische = abonnenten_statistik.juengste_messung(chosen)
            jetzt = datetime.now()
            for kuerzel, ts in frische.items():
                if ts is None:
                    veraltet[kuerzel] = -1.0
                    continue
                stunden = (jetzt - ts).total_seconds() / 3600.0
                if stunden > 24.0:
                    veraltet[kuerzel] = stunden
        except Exception:
            veraltet = {}
    uebersteuern = False
    if veraltet:
        teile = [f"**{k}**: {'nie gemessen' if h < 0 else f'letzte Messung vor {h:.0f} h'}"
                 for k, h in sorted(veraltet.items())]
        st.warning("Abonnentenzahlen nicht frisch (Schranke: maximal 24 h). "
                   "Betroffen: " + " · ".join(teile) + ". Bevorzugt zuerst oben "
                   "„Abonnentenzahlen aktualisieren“ mit „Frisch messen“ ausführen.",
                   icon=":material/history:")
        uebersteuern = st.checkbox(
            "Trotzdem mit veralteten Abonnentenzahlen starten",
            key="abonnenten_daten_veraltete_akzeptieren",
            help="Ausdrückliche Übersteuerung; der Lauf vermerkt die Übersteuerung "
                 "und die verwendeten Messzeitpunkte.")
    tradelisten_modus = st.radio(
        "Tradelisten", ["Nur fehlende laden (vorhandene behalten)", "Alle neu laden (überschreiben)"],
        help="Nur fehlende: bereits abgeschlossene Anbieter behalten ihre geladenen Trades "
             "und Kennzahlen — nach einem Abbruch wird nicht alles neu geladen. "
             "Alle neu laden: jeder Anbieter erhält eine frische Vollständigmessung "
             "seiner Tradeliste; alte Messwerte werden überschrieben.",
        key="abonnenten_daten_tradelisten")
    st.caption("Deterministische Vorauswertung: 70 % normierter Nettozuwachs und 30 % Jahres-RetDD. "
               "Normierung: Δ7 / durchschnittlicher positiver Abonnentenbestand der ursprünglichen Auswahl je Quelle.")
    if st.button("Datenauftrag starten", key="abonnenten_daten_start", type="primary",
                 disabled=not chosen or (bool(veraltet) and not uebersteuern)):
        try:
            run_id = _backend().daten_starten(
                chosen, retdd_gewicht=30, dd_grenze=None,
                tradelisten_modus=("fehlt" if tradelisten_modus.startswith("Nur fehlende") else "alle"),
                akzeptiere_veraltete_abos=uebersteuern)
            st.session_state["_abonnenten_daten_lauf_neu"] = run_id
            st.session_state["_abonnenten_daten_dialog"] = False
            st.rerun()
        except Exception as error:
            st.error(f"Datenauftrag nicht gestartet: {error}")


def render_daten_start_button() -> None:
    if st.button("Daten sammeln und Kennzahlen berechnen", key="abonnenten_daten_oeffnen",
                 type="primary", icon=":material/query_stats:"):
        st.session_state["_abonnenten_daten_dialog"] = True
    if st.session_state.get("_abonnenten_daten_dialog"):
        daten_dialog()


def _daten_polling(state: dict) -> bool:
    return state.get("workflow_modus") == _DATEN_MODUS and (
        bool(state.get("laeuft")) or state.get("status") == "geplant")


def render_daten_results() -> None:
    backend = _backend()
    runs = backend.laeufe()
    if not runs:
        return
    metadata = {str(run["id"]): run for run in runs}
    new_selection = st.session_state.pop("_abonnenten_daten_lauf_neu", None)
    if new_selection in metadata:
        st.session_state["abonnenten_daten_lauf"] = new_selection
    if st.session_state.get("abonnenten_daten_lauf") not in metadata:
        st.session_state["abonnenten_daten_lauf"] = next(iter(metadata))
    st.subheader("Stufe 1: Daten, Trades und Kennzahlen")
    options = list(metadata)
    selection_key = "abonnenten_daten_auswahl_" + sha256(repr(options).encode()).hexdigest()[:12]
    run_id = st.selectbox("Datenbestand", options, index=options.index(st.session_state["abonnenten_daten_lauf"]), key=selection_key,
                         format_func=lambda key: str(metadata[key].get("created_at") or "Zeitpunkt unbekannt") + " · " + key[:8])
    st.session_state["abonnenten_daten_lauf"] = run_id
    state = backend.zustand(run_id)
    polling = _daten_polling(state)

    @st.fragment(run_every=2.0 if polling else None)
    def results() -> None:
        nonlocal state
        # Reuse the first read needed to choose the interval; later fragment
        # reruns read fresh progress without loading the full entry list twice.
        current = state
        state = None
        if current is None:
            current = backend.zustand(run_id)
        if polling and not _daten_polling(current):
            # Only a full app run replaces the fragment's automatic timer.
            st.rerun(scope="app")
        _render_daten_results(backend, run_id, current)

    results()


def _render_daten_results(backend, run_id: str, state: dict) -> None:
    data_mode = state.get("workflow_modus") == _DATEN_MODUS
    model_only = state.get("modell_nur_bestand") is True
    running = data_mode and bool(state.get("laeuft"))
    entries = deepcopy(state.get("entries") or [])
    rank = getattr(backend, "rank_datamodus", None)
    if callable(rank):
        rank(entries, weight=30)
    else:
        for entry in entries:
            entry["rang"] = entry["auswahlwert"] = None
    entries.sort(key=lambda entry: (entry.get("rang") or 10**9, str(entry.get("quelle") or ""),
                                    str(entry.get("name") or ""), entry.get("id") or 0))
    state_view = {**state, "entries": entries, "auswahl_modus": _ZUFLUSS_MODUS}
    st.caption(f"Ausgewählter Datenbestand: {run_id} · gespeichert {state.get('updated_at') or 'Zeitpunkt unbekannt'}")
    if data_mode:
        fertig = sum(bool(e.get("data_done")) for e in entries)
        gesamt = len(entries)
        if running and gesamt and not model_only:
            # Progress-Balken (Nutzer-Wunsch 25.10.): Anteil fertiger
            # Daten-Endstände, live über das 2-s-Polling des Fragments.
            # Der reine Modellauftrag hat seinen eigenen Fortschritt.
            st.progress(min(fertig / gesamt, 1.0),
                        text=f"{state.get('phase') or 'arbeit'}: {fertig}/{gesamt} "
                             "Daten-Endstände")
        if model_only:
            st.caption("Modellauftrag: " + str(state.get("daten_status") or "geplant"))
            st.caption(f"Übernommene Messdaten: {fertig}/{gesamt} "
                       "gespeicherte Daten-Endstände; dieser Zähler ist nicht der Modellfortschritt.")
        else:
            modus = ("Modus: Alle neu laden (jeder Anbieter wird frisch vermessen)"
                     if state.get("tradelisten_modus") == "alle"
                     else "Modus: Nur fehlende laden (fertige bleiben)")
            st.caption("Datenauftrag: " + str(state.get("daten_status") or "geplant")
                       + f" · {fertig}/{gesamt} Daten-Endstände · " + modus)
        if state.get("daten_workflow_abgeschlossen"):
            (st.success if state.get("daten_vollstaendig") else st.warning)(
                ("Modellberechnung aus Bestand beendet; alle benötigten Werte berechnet." if model_only
                 else "Datenablauf beendet; alle benötigten Daten vorhanden.") if state.get("daten_vollstaendig")
                else ("Modellberechnung aus Bestand beendet; offene Modellpunkte stehen in der Tabelle." if model_only
                      else "Datenablauf beendet; offene Datenpunkte stehen weiterhin in der Tabelle."))
        if running:
            # Zahlen am Button (Nutzer-Wunsch 25.10.): Sofort sichtbar, wie
            # viel geladen ist und wie viel offen bleibt.
            if st.button(("Berechnung aus Bestand stoppen" if model_only else "Datensammlung stoppen")
                         + f" — {fertig}/{gesamt} geladen", key=f"abonnenten_daten_stop_{run_id}"):
                backend.stoppen(run_id)
                st.rerun()
        elif not state.get("daten_vollstaendig"):
            offen = max(gesamt - fertig, 0)
            if st.button(("Berechnung aus Bestand fortsetzen" if model_only else "Datensammlung fortsetzen")
                         + f" — {fertig}/{gesamt} geladen, {offen} offen",
                         key=f"abonnenten_daten_resume_{run_id}"):
                try:
                    backend.daten_fortsetzen(run_id)
                    st.rerun()
                except Exception as error:
                    st.error(f"Datensammlung nicht fortgesetzt: {error}")
    else:
        st.caption("Vorhandene gespeicherte Daten werden sofort lesend angezeigt. "
                   "Für weitere Beschaffung zuerst einen eigenen Datenauftrag übernehmen.")
        if st.button("Gespeicherten Datenbestand als Datenauftrag übernehmen", key=f"abonnenten_daten_clone_{run_id}"):
            try:
                new_id = backend.daten_aus_lauf(run_id, fortsetzen=False)
                st.session_state["_abonnenten_daten_lauf_neu"] = new_id
                st.rerun()
            except Exception as error:
                st.error(f"Datenbestand nicht übernommen: {error}")
    # Nutzer-Entscheidung 24.10. abends: Der separate Start einer „Modellberechnung
    # aus Bestand" (Trades unverändert, keine Beschaffung) ist entfernt. Der
    # Datenauftrag lädt selbst Tradelisten und berechnet alles; ein Abbruch wird
    # über den Tradelisten-Modus „nur fehlende" fortgesetzt. Historische
    # Bestandsläufe bleiben abwärtskompatibel lesbar (modell_nur_bestand-Anzeige).
    models = [entry["modell"] for entry in entries if isinstance(entry.get("modell"), dict)]
    show_models = bool(models) or state.get("kapitalmodell_aktiv") is True
    st.caption("Alle ausgewählten Anbieter bleiben sichtbar, einschließlich unvollständiger Daten. "
               + ("Vorauswertung: 70 % normierter Nettozuwachs und 30 % Modell-Jahres-RetDD; Modellwerte sind keine Kontomessung."
                  if show_models else "Vorauswertung: 70 % normierter Nettozuwachs und 30 % Jahres-RetDD; keine zusätzliche Freigabe."))
    if show_models:
        counts = Counter(model.get("status") or "unbekannt" for model in models)
        processed = _number(state.get("modell_bearbeitet"))
        if processed is not None:
            st.caption(f"Modellbearbeitung: {int(processed)}/{len(entries)} Anbieter")
            st.progress(min(1.0, max(0.0, processed / len(entries))) if entries else 0.0)
        if state.get("modell_abgeschlossen"):
            def count(key, field, *, positive=False):
                saved = _number(state.get(key))
                if saved is not None:
                    return int(saved)
                return sum((value := _number(model.get(field))) is not None
                           and (not positive or value > 0) for model in models)
            with st.container(horizontal=True):
                st.metric("Modell-Startkapital", f"{count('modell_anzahl_mit_startkapital', 'startkapital_usd', positive=True)}/{len(entries)}")
                st.metric("Modell-Floating-DD", f"{count('modell_anzahl_mit_dd', 'equity_dd_pct')}/{len(entries)}")
                st.metric("Modell-Jahres-RetDD", f"{count('modell_anzahl_mit_retdd', 'retdd_jahr')}/{len(entries)}")
        st.caption("Modellszenario: keine Ein-/Auszahlungen, auch bekannte Kapitalflussereignisse werden ignoriert. "
                   "Kapitalbasis und Herkunft sind je Anbieter gekennzeichnet; die Basis kann eine Lotschätzung, "
                   "grobe Lotschätzung oder 10.000-USD-Annahme sein. Fehlende Modell-DD-/RetDD-Werte bleiben leer.")
        st.caption("Modell-Jahresrendite und Modell-Jahres-RetDD sind annualisierte Szenariowerte, "
                   "keine beobachteten Jahresergebnisse des ursprünglichen Kontos.")
        st.caption(f"Modellstatus: {counts['berechnet']} berechnet · {counts['eingeschraenkt']} eingeschränkt · "
                   f"{counts['datenluecke']} Datenlücken. Echte Messungen bleiben getrennt im Detail und CSV erhalten.")
    st.caption(("Modell-DD: maximaler berechneter relativer Floating-Equity-Rückgang vom zuvor erreichten Modellhoch; "
                "kein Nachweis des tatsächlichen Kontoverlaufs. " if show_models else
                "DD: maximaler gemessener relativer Floating-Equity-Rückgang vom zuvor erreichten Hoch. ")
               + "Berechnungsfenster: alle verfügbaren exportierten geschlossenen Positionen an H1-Bar-Schlüssen. "
               "Intrabar-Tiefs und aktuell offene Positionen sind nicht vollständig erfasst; unbekannte Werte bleiben leer.")
    coverage = daten_quellenabdeckung(state_view)
    if not coverage.empty:
        with st.expander("Quellenabdeckung und offene Datenpunkte"):
            st.caption("Historischer Auftragsstand, kein aktueller Verbindungs- oder Loginstatus. "
                       "Quellengewinn ist keine eigene Equity-/RetDD-Messung.")
            st.table(coverage)
    table = daten_tabelle(entries, state_view)
    if table.empty:
        st.info("Noch keine Anbieter in diesem Datenauftrag gespeichert.")
        return
    main_values = (["Modell-Startkapital USD", "Modell-Kapitalbasis/Herkunft", "Modell-Nettogewinn USD",
                   "Modell-Rendite Exportfenster %", "Modell-Equity-DD inkl. Floating %", "Modell-Jahres-RetDD",
                   "Modell-Trades", "Modell-H1-Abdeckung %", "Modellstatus", "Modellgrund"] if show_models
                   else ["Nettogewinn USD", "Rendite Exportfenster %", "Max. gemessener Equity-DD %", "Jahres-RetDD"])
    selected = st.dataframe(table, hide_index=True, placeholder="", width="stretch", height=min(650, 40 + 35 * len(table)),
        key=f"abonnenten_daten_tabelle_{run_id}", selection_mode="single-row", on_select="rerun",
        column_order=["Quelle", "Strategie", "Link", "Abonnenten", "Nettozuwachs 7 Tage", "Zufluss / Quellenmittel", *main_values,
            "Monate", "Trades", "Trade-Export-Status", "Abdeckungsstatus", "Status", "Grund", "Quellengewinn USD", "Quellrendite %",
            "Datenrang", "Vorauswertung", "Auswahlhinweis"],
        column_config={"Link": st.column_config.LinkColumn(
                "Link", width=48, display_text="↗",
                help="Öffnet die Signalseite beim Broker (MQL5, ZuluTrade, "
                     "Vantage, Pelican, RoboForex) in einem neuen Browser-Tab"),
            "Max. gemessener Equity-DD %": st.column_config.NumberColumn(format="%.2f %%"),
            "Status": st.column_config.TextColumn("Status der Messdaten" if show_models else "Status"),
            "Grund": st.column_config.TextColumn("Offene Messdatenpunkte" if show_models else "Grund"),
            "Abdeckungsstatus": st.column_config.TextColumn("Abdeckung der Messdaten" if show_models else "Abdeckungsstatus"),
            "Rendite Exportfenster %": st.column_config.NumberColumn(format="%.2f %%"),
            "Nettogewinn USD": st.column_config.NumberColumn(format="%.2f USD"),
            "Jahres-RetDD": st.column_config.NumberColumn(format="%.2f"),
            "Modell-Startkapital USD": st.column_config.NumberColumn(format="%.2f USD"),
            "Modell-Equity-DD inkl. Floating %": st.column_config.NumberColumn(format="%.2f %%"),
            "Modell-Jahres-RetDD": st.column_config.NumberColumn(format="%.2f"),
            "Zufluss / Quellenmittel": st.column_config.NumberColumn(format="%.4f")})
    chosen_rows = getattr(getattr(selected, "selection", None), "rows", [])
    if chosen_rows and 0 <= chosen_rows[0] < len(entries):
        _render_daten_detail(entries[chosen_rows[0]], state_view)
    st.download_button("Messwerte als CSV", daten_csv(entries, state_view), f"abonnenten-daten-{run_id}.csv",
                       "text/csv", key=f"abonnenten_daten_csv_{run_id}")
