# -*- coding: utf-8 -*-
"""Scan-Arbeitsplatz: ein Workflow von MQL5-Daten bis zum KI-Bericht.

Der Lauf läuft in einem Hintergrund-Thread (st.session_state.scan_thread),
damit die Oberfläche bedienbar bleibt: Der Stop-Button setzt ein Flag
(st.session_state.scan_control["stop"]) und der Lauf endet sauber zwischen
zwei Signalen bzw. Modellaufrufen. Der Thread fasst NUR einfache Dicts/Listen
an (workflow, logs, results, control) — kein st.* im Worker-Thread.

Live-Status ohne Flimmern: Der Statusbereich ist ein st.fragment mit
run_every — beim Tick wird NUR dieser Bereich neu gerendert, nicht die
ganze Seite. Ist der Lauf fertig, löst das Fragment einmal einen vollen
App-Rerun aus (Ergebnisse übernehmen + Endstand rendern).
"""
from __future__ import annotations

import html
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, db, pipeline, scan_state, scan_worker, secrets_store
from mqlkiscanner.app_ui import (
    render_portfolio_pdf_viewer,
    render_report_panel,
    render_results_table,
)
from mqlkiscanner.ui_design import (
    action_button, apply_theme, page_header, section_header, urteile_farbig,
    workflow_stepper_html,
)

apply_theme()

# Interne Status-Schritte (IDs stabil für Pipeline/Tests). Letztes Element =
# Laien-Beschreibung, die in der Stationskarte mit angezeigt wird.
STEPS = (
    ("listen", "Signale holen", "cloud_download", "Seiten",
     "Signallisten und Handelsdaten von MQL5 laden"),
    ("kandidaten", "Auswahl treffen", "filter_list", "Signale",
     "Alter und Abonnenten prüfen, ungeeignete aussortieren"),
    ("forensik", "Prüfen & speichern", "database", "Datensätze",
     "Webseite und CSV auf Risiko rechnen, alles in die Datenbank"),
    ("llm", "KI-Bericht", "psychology", "Berichte",
     "Verständliche Texte und Endbericht je Signal schreiben"),
    ("portfolio", "Portfolio", "pie_chart", "Vorschlag",
     "Alle Berichte zusammenführen: Welche Strategien passen ins Depot?"),
)
STATES = {
    "pending": ("Wartet", "gray", "schedule"),
    "running": ("Läuft", "blue", "autorenew"),
    "complete": ("Fertig", "green", "check_circle"),
    "warning": ("Mit Hinweisen", "orange", "warning"),
    "error": ("Fehlgeschlagen", "red", "error"),
    "skipped": ("Übersprungen", "gray", "skip_next"),
}


def _new_workflow(mode: str | None = None) -> dict:
    return {
        "mode": mode, "status": "running" if mode else "idle",
        "started_at": datetime.now().isoformat(timespec="seconds") if mode else None,
        "finished_at": None, "activity": "Bereit. Starten Sie die Analyse.",
        "activity_at": None, "saved": False,
        "steps": {sid: {"status": "pending", "done": 0, "total": None,
                        "detail": "Noch nicht gestartet", "unit": unit}
                  for sid, _, _, unit, _ in STEPS},
    }


st.session_state.setdefault("scan_results", [])
st.session_state.setdefault("scan_logs", {})
st.session_state.setdefault("last_run_file", None)
st.session_state.setdefault("scan_workflow", _new_workflow())
st.session_state.setdefault("portfolio_bericht", "")
st.session_state.setdefault("portfolio_result", None)
st.session_state.setdefault("scan_new_ids", [])
st.session_state.setdefault("scan_thread", None)
st.session_state.setdefault("scan_control", {})


def _stop_requested() -> None:
    """Button-Callback: Stop-Flag für den Worker setzen."""
    ctl = st.session_state.get("scan_control") or {}
    ctl["stop"] = True
    wf = st.session_state.get("scan_workflow")
    if wf:
        wf["activity"] = "Stop angefordert — der Lauf endet nach dem aktuellen Signal bzw. Modellaufruf."


def _attach_worker(run: scan_worker.WorkerRun) -> None:
    """Nach Browser-Reload denselben Prozess-Worker wieder sichtbar machen."""
    scan_state.attach_worker(st.session_state, run)


reattached = scan_state.sync_worker_state(st.session_state)
command = st.session_state.pop("scan_command", None)
shared_run = scan_worker.active_run()
if shared_run is not None:
    _attach_worker(shared_run)
    # Auch bereits abgesendete Befehle aus einer zweiten Sitzung abweisen.
    command = None
workflow = st.session_state.scan_workflow
control = st.session_state.scan_control
_lauf_thread = st.session_state.scan_thread
_thread_lebt = bool(_lauf_thread is not None and _lauf_thread.is_alive())

# Altlast ohne Thread-Objekt (z. B. nach App-Neustart mitten im Lauf):
# einen hängenden "running"-Stand nicht weiter als aktiv anzeigen.
if command is None and _lauf_thread is None and workflow["status"] == "running":
    for step in workflow["steps"].values():
        if step["status"] == "running":
            step.update(status="error", detail="Lauf unterbrochen; nicht abgeschlossen")
        elif step["status"] == "pending":
            step.update(status="skipped", detail="Nach Unterbrechung nicht ausgeführt")
    workflow.update(status="error", activity="Lauf unterbrochen. Vorliegende Ergebnisse bleiben erhalten.",
                    finished_at=datetime.now().isoformat(timespec="seconds"))
    st.session_state.scan_running = None
if command:
    workflow = _new_workflow(command["mode"])
    st.session_state.scan_workflow = workflow
    st.session_state.portfolio_result = None
    st.session_state.portfolio_bericht = ""
    if command["mode"] in ("scan", "step_listen"):
        st.session_state.scan_signals = []
    if command["mode"] in ("scan", "step_listen", "step_kandidaten"):
        # Nachgelagerte Daten gehören zur vorherigen Auswahl. Auch bei einem
        # Fehler im neuen Abruf dürfen sie nicht als neuer Stand weiterlaufen.
        st.session_state.scan_candidates = []
    if command["mode"] == "scan" and command["settings"] and not (
            config.llm_aktiv(command["settings"])):
        workflow["steps"]["llm"].update(status="skipped", detail="KI-Berichte für diesen Lauf ausgeschaltet")
        workflow["steps"]["portfolio"].update(status="skipped", detail="Portfolio-Vorschlag für diesen Lauf ausgeschaltet")
    if command["mode"] in ("scan", "step_listen"):
        st.session_state.scan_results = []
        st.session_state.scan_logs = {}
        st.session_state.last_run_file = None
        st.session_state.portfolio_bericht = ""
    if command["mode"] in ("local", "step_kandidaten", "step_forensik"):
        # Eine neue Prüfung ersetzt die vorherige Ergebnismenge dieser Sitzung.
        st.session_state.scan_results = []
        st.session_state.portfolio_bericht = ""
    if command["mode"] in ("scan", "local", "step_forensik"):
        st.session_state.scan_new_ids = []

settings = config.load_settings()
running = command is not None or _thread_lebt
hero_banner = Path(__file__).resolve().parents[1] / "assets" / "hero_scan_banner.jpg"
page_header(
    "RISIKOPRÜFUNG",
    "MQL5-Signale belastbar prüfen",
    "Eine Analyse verbindet Handelsdaten, forensische Risikotests und optional "
    "KI-Berichte. **Schutz muss belegt sein; 30 % Drawdown ist die harte Grenze.**",
    image_path=str(hero_banner) if hero_banner.exists() else None,
)
if reattached:
    st.info("Ein Workflow läuft bereits im Hintergrund. Der laufende Prozess wurde "
            "wieder verbunden; Status und Stop-Button steuern denselben Lauf.")
section_header(
    "Analyse starten",
    "Ein Start, fünf nachvollziehbare Stationen, ein gespeicherter Ergebnisstand.",
    help_key="scan_workflow",
)


def _step_fraction(step: dict) -> float:
    """Anteil 0..1 einer Station: beendet = 1, laufend = done/total, sonst 0."""
    status = step["status"]
    if status in ("complete", "warning", "error", "skipped"):
        return 1.0
    if status == "running" and step["total"]:
        return min(step["done"] / step["total"], 1.0)
    return 0.0


def _mmss(secs: float) -> str:
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _elapsed_text(workflow: dict) -> str:
    started = workflow.get("started_at")
    if not started:
        return ""
    try:
        start_dt = datetime.fromisoformat(started)
        end_dt = (datetime.fromisoformat(workflow["finished_at"])
                  if workflow.get("finished_at") else datetime.now())
    except ValueError:
        return ""
    return _mmss((end_dt - start_dt).total_seconds())


def _stamped(text: str) -> str:
    """Log-Zeile mit Uhrzeit-Präfix — auch im gespeicherten Protokoll nachvollziehbar."""
    return f"{datetime.now().strftime('%H:%M:%S')} · {text}"


def _station_kennzahlen(results) -> tuple[int, int, int]:
    """(entschieden, nur Vorprüfung, Probleme) für die Forensik-Station.

    Entscheiden heißt: die Ampel trägt ein fertiges Urteil (🟢 🟡 🔴 ⛔) —
    auch ein Signal, das wegen negativer Kapitalbasis oder ohne Forensik
    hart abgelehnt wurde, ist damit GEPRÜFT und zählt nicht als Problem.
    Probleme sind ausschließlich ⚪-Ampeln mit Fehlermeldung (Prüfung
    gescheitert), Vorprüfung ⚪-Ampeln ohne Fehlermeldung.
    """
    entschieden = sum(r.ampel in ("🟢", "🟡", "🔴", "⛔") for r in results)
    probleme = sum(r.ampel == "⚪" and bool(r.fehler) for r in results)
    return entschieden, len(results) - entschieden - probleme, probleme


def _recent_log_lines(n: int = 3) -> list[str]:
    lines: list[str] = []
    logs = st.session_state.get("scan_logs") or {}
    for sid, *_rest in STEPS:
        lines.extend(logs.get(sid) or [])
    return lines[-n:]


@st.fragment(run_every=1.0)
def _live_status() -> None:
    """Live-Bereich (Fragment): jede Sekunde NUR Statuszeile, Balken und Stepper neu zeichnen."""
    workflow = st.session_state.scan_workflow
    # Snapshot: Der Worker-Thread darf while wir rendern in das Dict schreiben.
    steps_state = {sid: dict(step) for sid, step in workflow["steps"].items()}
    overall = sum(_step_fraction(s) for s in steps_state.values()) / len(STEPS)
    status = workflow["status"]
    laufend = next(((sid, nr, title) for nr, (sid, title, *_rest) in enumerate(STEPS, 1)
                    if steps_state[sid]["status"] == "running"), None)

    # Statuszeile: Was läuft gerade, wie lange schon.
    dot = {"running": "running", "complete": "complete",
           "warning": "warning", "error": "error"}.get(status, "")
    if status == "running":
        headline = (f"Station {laufend[1]} von {len(STEPS)} · {laufend[2]}"
                    if laufend else "Workflow startet …")
    else:
        headline = {
            "idle": "Bereit für die Analyse",
            "complete": "Workflow beendet — alle Stationen durch",
            "warning": "Workflow beendet — mit Hinweisen",
            "error": "Workflow beendet — mit Fehlern",
        }.get(status, "Bereit")
    # Idle: Überschrift ruft schon zum Start auf — Aktivitätstext wäre Doppelt.
    activity = "" if status == "idle" else (workflow.get("activity") or "")
    # Stoppuhr der aktuellen Meldung: zählt hoch, bis der Worker die nächste
    # Meldung schreibt — sichtbarer Herzschlag auch bei Minuten langen
    # Modell-Aufrufen (ältere Läufe ohne activity_at zeigen keinen Chip).
    warte = None
    activity_at = workflow.get("activity_at")
    if status == "running" and activity_at:
        warte = max(0, int(time.time() - float(activity_at)))
        if activity and warte >= 120:
            activity += (f" — bereits {_mmss(warte)} keine neue Meldung; "
                         "meist wartet der Scanner auf die Antwort des KI-Modells.")
    # Futuristisches Backlight: Während des Laufs leuchtet das ganze Panel.
    # Identischer Inhalt je Tick, damit Streamlit das <style>-Element nicht
    # neu erzeugt und die Puls-Animation ungestört weiterläuft.
    if status == "running" or laufend:
        st.markdown(
            "<style>"
            ".st-key-scan_control_panel > div { position: relative; "
            "border-color: rgba(0,210,211,.72) !important; }"
            ".st-key-scan_control_panel > div::after {"
            " content: ''; position: absolute; inset: -2px; border-radius: 16px;"
            " border: 2px solid rgba(0,210,211,.6);"
            " box-shadow: 0 0 24px rgba(0,210,211,.32),"
            " 0 0 70px rgba(0,210,211,.16),"
            " inset 0 0 30px rgba(0,210,211,.14);"
            " animation: mks-backlight 2.4s ease-in-out infinite;"
            " pointer-events: none; }"
            "</style>",
            unsafe_allow_html=True,
        )
    strip = [
        '<div class="mks-strip">',
        f'<div class="mks-strip__main"><span class="mks-dot mks-dot--{dot}" aria-hidden="true"></span>'
        f'<div class="mks-strip__text"><b>{html.escape(headline)}</b>',
    ]
    if activity:
        strip.append(f"<small>{html.escape(activity)}</small>")
    strip.append("</div></div>")
    chips = []
    if clock := _elapsed_text(workflow):
        chips.append(
            f'<span class="mks-clock" title="Summe der Laufzeit aller Stationen">'
            f'Σ Gesamt {clock}</span>')
    llm_step = steps_state["llm"]
    if llm_step["status"] == "running" and llm_step.get("signal_total"):
        chips.append(
            f'<span class="mks-clock" title="Aktuell bearbeitetes Signal von allen '
            f'Signalen, für die neue KI-Berichte erstellt werden">'
            f'Signale {llm_step.get("signal_current", 0)}/{llm_step["signal_total"]}</span>')
    if warte is not None:
        is_llm_wait = bool(laufend and laufend[0] in ("llm", "portfolio"))
        wait_label = "LLM-Antwort" if is_llm_wait else "Aktueller Schritt"
        wait_title = (
            "Wartezeit auf die aktuelle LLM-Antwort; zählt bis zur nächsten "
            "Modellantwort oder Statusmeldung."
            if is_llm_wait else
            "Laufzeit der aktuellen Meldung; zählt bis zum nächsten Arbeitsschritt."
        )
        chips.append(
            f'<span class="mks-clock mks-clock--wait" title="{wait_title}">'
            f'{wait_label} {_mmss(warte)}</span>')
    if chips:
        strip.append(f'<div class="mks-strip__side">{"".join(chips)}</div>')
    strip.append("</div>")
    st.markdown("".join(strip), unsafe_allow_html=True)

    # Gesamtfortschritt über alle Stationen (nur anzeigen, wenn ein Lauf existiert).
    if workflow.get("started_at"):
        fertig = sum(s["status"] in ("complete", "warning", "error", "skipped")
                     for s in steps_state.values())
        st.progress(
            overall,
            text=(f"Gesamtfortschritt {int(round(overall * 100))} % · "
                  f"{fertig} von {len(STEPS)} Stationen abgeschlossen"),
        )

    # Stations-Stepper: Nummernkreis je Station, Schiene = Gesamtfortschritt.
    first_pending = next((sid for sid, *_rest in STEPS
                          if steps_state[sid]["status"] == "pending"), None)
    payload = []
    for nr, (sid, title, _icon, _unit, beschreibung) in enumerate(STEPS, 1):
        step = steps_state[sid]
        payload.append({
            "nr": nr, "title": title, "status": step["status"],
            "label": STATES[step["status"]][0],
            "meta": step.get("detail") if step["status"] != "pending" else beschreibung,
            "frac": _step_fraction(step) if step["status"] == "running" else None,
            "hint": sid == first_pending and status != "running",
        })
    st.markdown(workflow_stepper_html(payload, overall), unsafe_allow_html=True)

    # Letzte Meldungen statt Logfile-Wand: kurz beweisen, dass sich was tut.
    recent = _recent_log_lines()
    if recent:
        st.markdown(
            '<div class="mks-feed" aria-label="Letzte Meldungen">'
            + "".join(f'<div class="mks-feed__line">{html.escape(line)}</div>'
                      for line in recent)
            + "</div>",
            unsafe_allow_html=True,
        )

    # Lauf beendet? Einmal die GANZE Seite neu laden: Ergebnisübernahme
    # (Session) + Endstand (Tabelle, Portfolio) rendern.
    th = st.session_state.scan_thread
    if (th is not None and not th.is_alive()
            and st.session_state.get("_copied_scan_control") is not st.session_state.scan_control):
        st.rerun(scope="app")


has_login = bool(secrets_store.get_secret("mql5_user") and secrets_store.get_secret("mql5_pass"))
has_llm = bool(secrets_store.get_secret("glm_api_key"))
with st.container(border=True, key="scan_control_panel"):
    with st.container(horizontal=True, gap="small"):
        st.badge("MQL5 bereit" if has_login else "MQL5-Zugang fehlt",
                 icon=":material/lock:", color="green" if has_login else "orange")
        st.badge("KI-Berichte aktiv" if has_llm else "KI optional",
                 icon=":material/psychology:", color="green" if has_llm else "gray")
    start_zeile = st.columns([1.25, 1], gap="small", vertical_alignment="center")
    with start_zeile[0]:
        start = action_button(
            "Analyse starten",
            key="scan_start",
            help_key="scan_start",
            type="primary",
            icon=":material/play_arrow:",
            disabled=running,
        )
    with start_zeile[1]:
        if running:
            schon = bool(st.session_state.scan_control.get("stop"))
            st.button(
                "Stop angefordert …" if schon else "Workflow stoppen",
                key="scan_stop",
                icon=":material/stop_circle:",
                disabled=schon,
                on_click=_stop_requested,
                help="Stoppt sauber nach dem aktuellen Signal bzw. Modellaufruf — "
                     "kein harter Abbruch, fertige Teilergebnisse bleiben erhalten.",
            )
        else:
            st.caption("Die fünf Stationen laufen automatisch. Sie können den Lauf jederzeit "
                       "kontrolliert stoppen.")

    _live_status()
    if not has_login:
        st.warning(
            "Ohne MQL5-Zugang ist nur eine Vorprüfung möglich. Für belastbare "
            "Stop- und Exposure-Befunde zuerst den Zugang unter Einstellungen ergänzen.",
            icon=":material/warning:",
        )
    else:
        st.caption(
            f"Kontoschonender Abruf: mindestens {settings['rate_min_interval_s']:.1f} s "
            f"zwischen Anfragen und {settings['rate_pause_zwischen_signalen_s']:.1f} s "
            "Pause je Signal."
        )

with st.expander("Analyseumfang anpassen", icon=":material/tune:", expanded=False):
    with st.container(border=True):
        section_header(
            "Bereits geprüfte Signale",
            "Standardmäßig werden vorhandene Bewertungen wiederverwendet.",
            help_key="scan_reuse",
        )
        nur_neue = st.toggle(
            "Nur neue Signale laden; vorhandene Bewertungen übernehmen",
            key="scan_nur_neue",
            disabled=running,
        )
        st.caption(
            "Spart Zeit und MQL5-Anfragen. Fehlende oder veraltete KI-Berichte werden "
            "trotzdem ergänzt; der Portfolio-Vorschlag berücksichtigt alle Signale."
        )
    left, right = st.columns(2)
    with left.container(border=True, key="scan_scope"):
        section_header("Wie weit suchen?", "Weniger Seiten = schnellerer Lauf.", help_key="scan_scope")
        pages = st.number_input(
            "Listen-Seiten je MT4/MT5", *config.SCAN_INPUT_BOUNDS["listen_seiten"], value=int(settings["listen_seiten"]),
            key="set_seiten", disabled=running)
        top_n = st.number_input(
            "Max. Signale gründlich prüfen", *config.SCAN_INPUT_BOUNDS["top_n_export"], value=int(settings["top_n_export"]),
            key="set_topn", disabled=running)
    with right.container(border=True, key="scan_filters"):
        section_header("Vorfilter", "Nur Signale, die alt genug und sichtbar genug sind.",
                       help_key="scan_filters")
        min_weeks = st.number_input(
            "Mindestalter in Wochen", *config.SCAN_INPUT_BOUNDS["min_wochen"], value=int(settings["min_wochen"]),
            key="set_wochen", disabled=running)
        min_subs = st.number_input(
            "Mindestens Abonnenten", *config.SCAN_INPUT_BOUNDS["min_abonnenten"], value=int(settings["min_abonnenten"]),
            key="set_abo", disabled=running)
    with st.container(border=True, key="scan_llm_settings"):
        section_header("KI am Ende?", "Nach dem Rechnen drei Berichte je Signal, danach der Portfolio-Vorschlag.",
                       help_key="scan_llm_settings")
        use_llm = st.toggle(
            "KI-Berichte nach dem Workflow erstellen",
            key="scan_use_llm",
            value=config.llm_aktiv(settings),
            disabled=running,
        )
        st.caption("Trade- und Risiko-Analyse parallel, danach der Endbericht — "
                   "zum Schluss der Portfolio-Vorschlag über alle Signale.")
        berichte_neu = st.toggle(
            "Vorhandene Berichte neu erstellen",
            key="scan_llm_neu",
            value=False,
            disabled=running,
        )
        st.caption(
            "Aus (Standard): Signale mit einem zur aktuellen Bewertungsbasis passenden "
            "Gesamtbericht werden übersprungen — ihr Bericht wird aus der Datenbank geladen. "
            "An: alle Berichte werden neu erzeugt (Dauer + Tokens)." if not berichte_neu else
            "An: ALLE Berichte werden neu erzeugt — vorhandene werden ersetzt "
            "(in der Datenbank bleibt die Historie erhalten)."
        )
    st.caption("Diese Werte gelten für den nächsten Lauf. Speichern übernimmt sie als Standard.")
    save_settings = action_button(
        "Einstellungen als Standard speichern",
        key="scan_save",
        help_key="scan_save",
        icon=":material/save:",
        disabled=running,
    )
    st.caption(
        f"Abrufabstand: {settings['rate_min_interval_s']:.1f} s · "
        f"Pause je Signal: {settings['rate_pause_zwischen_signalen_s']:.1f} s")

with st.expander("Testdaten und Expertenfunktionen", icon=":material/build:", expanded=False):
    st.caption("Für Diagnose und gezielte Teilläufe; im Normalfall nicht erforderlich.")
    vcol, lcol = st.columns(2, gap="small")
    with vcol.container(border=True, key="scan_source_local", height="stretch"):
        st.markdown(":material/fact_check: **Nur Testdaten prüfen**")
        st.caption("Vorhandene Dateien in data/raw analysieren — ohne Internet und ohne neue KI.")
        st.caption("Demo-Ergebnisse bleiben getrennt vom Live-Katalog und werden nicht für KI-Berichte verwendet.")
        verify = action_button(
            "Testdaten laden",
            key="scan_verify",
            help_key="scan_verify",
            icon=":material/fact_check:",
            disabled=running,
        )
    with lcol.container(border=True, key="scan_source_llm", height="stretch"):
        st.markdown(":material/psychology: **Nur KI nachziehen**")
        st.caption("Bereits geprüfte Ergebnisse dieser Sitzung mit KI erklären — "
                   "inklusive Portfolio-Vorschlag.")
        llm_only = action_button(
            "KI-Berichte starten",
            key="scan_llm",
            help_key="scan_llm",
            icon=":material/psychology:",
            disabled=running or not any(getattr(r, "source_kind", "live") == "live"
                                        for r in st.session_state.scan_results),
        )
    st.markdown("**Einzelschritte (Experten)**")
    st.caption("Normalerweise unnötig. Der Workflow-Button führt alle Stationen automatisch aus.")
    step_cols = st.columns(len(STEPS), gap="small")
    for nr, (col, (sid, title, *_rest)) in enumerate(zip(step_cols, STEPS), 1):
        with col:
            if st.button(
                f"Nur Station {nr}",
                key=f"step_btn_{sid}",
                disabled=running,
                icon=":material/play_arrow:",
                help=title,
            ):
                st.session_state.scan_command = {"mode": f"step_{sid}", "settings": None}
                st.rerun()

run_settings = {
    **settings,
    "listen_seiten": int(pages),
    "top_n_export": int(top_n),
    "min_wochen": int(min_weeks),
    "min_abonnenten": int(min_subs),
    "llm_stufe1": bool(use_llm),
    "llm_stufe2": bool(use_llm),
    "nur_neue": bool(nur_neue),       # Lauf-Modus, wird nicht als Standard gespeichert
    "berichte_neu": bool(berichte_neu),  # dito: vorhandene Berichte neu erzeugen
}
if save_settings:
    config.save_settings({k: v for k, v in run_settings.items()
                          if k not in ("nur_neue", "berichte_neu")})
    st.toast("Einstellungen gespeichert.", icon=":material/check:")
if start or verify or llm_only:
    st.session_state.scan_command = {
        "mode": "scan" if start else "local" if verify else "llm",
        "settings": run_settings,
    }
    st.rerun()


# ---------------------------------------------------------- Workflow-Lauf
# Der Worker-Thread führt die Stationen aus und fasst NUR einfache Objekte an
# (workflow-, control-, logs-Dict, results-Liste). Rendern tut ausschließlich
# die Seite (Inline) bzw. das Fragment (Tick alle 1 s).
if command:
    run_config = command["settings"] or run_settings
    mode = command["mode"]
    logs = st.session_state.scan_logs
    results = st.session_state.scan_results
    signals_vorhanden = st.session_state.get("scan_signals")
    candidates_vorhanden = st.session_state.get("scan_candidates")
    control = {"stop": False, "portfolio_bericht": "", "portfolio": None, "new_ids": [],
               "signals": signals_vorhanden or [], "candidates": candidates_vorhanden or [],
               "last_run_file": None, "refreshed_ids": [], "copied": False}
    st.session_state.scan_control = control
    st.session_state.scan_running = mode if mode != "scan" else "listen"
    pipe = pipeline.ScanPipeline(run_config)

    def _touch_activity(text: str) -> None:
        """Neue Aktivität melden: Text plus Startzeitpunkt der Stoppuhr."""
        workflow["activity"] = text
        workflow["activity_at"] = time.time()

    def w_step(sid: str, status: str | None = None, **values) -> None:
        if status:
            values["status"] = status
        workflow["steps"][sid].update(values)
        if "detail" in values:
            _touch_activity(values["detail"])

    def w_log_for(sid: str):
        lines = logs.setdefault(sid, [])

        def log(message: str) -> None:
            lines.append(_stamped(message))
            _touch_activity(message.splitlines()[0][:400])
        return log

    def w_skip_if_stopped(sid: str) -> bool:
        if not control.get("stop"):
            return False
        w_step(sid, "skipped", detail="Abbruch per Stop-Button vor dieser Station")
        return True

    def w_run_listen(cfg) -> list[dict]:
        if w_skip_if_stopped("listen"):
            return []
        w_step("listen", "running", total=2 * cfg["listen_seiten"],
               detail="MQL5-Listen abrufen …")
        signals = pipe.crawl(
            on_progress=lambda done, total, text: w_step("listen", done=done, total=total, detail=text),
            log=w_log_for("listen"),
        )
        control["signals"] = signals
        w_step("listen", "complete", detail=f"{len(signals)} Signale geladen")
        return signals

    def w_run_kandidaten(signals: list[dict], cfg) -> list[dict]:
        if w_skip_if_stopped("kandidaten"):
            return []
        w_step("kandidaten", "running", total=len(signals),
               detail="Alter und Abonnenten prüfen …")
        candidates = pipe.build_candidates(signals, w_log_for("kandidaten"))
        control["candidates"] = candidates
        w_step("kandidaten", "complete", done=len(signals),
               detail=f"{len(candidates)} passende Signale aus {len(signals)}")
        return candidates

    def w_run_forensik(cands: list[dict], cfg) -> None:
        if w_skip_if_stopped("forensik"):
            return
        n_export = min(len(cands), cfg["top_n_export"])
        if not n_export:
            w_step("forensik", "skipped", detail="Keine passenden Signale nach der Auswahl")
            return
        only_new = bool(cfg.get("nur_neue"))
        alt: dict[int, pipeline.ScanResult] = {}
        if only_new:
            alt = {r.id: r for r in pipeline.results_from_db(cfg) if r.forensik_vorhanden
                   and getattr(r, "source_kind", "live") == "live"}
        scope = cands[:n_export]
        neu = [c for c in scope if c["id"] not in alt] if only_new else scope
        uebernommen = [alt[c["id"]] for c in scope if c["id"] in alt]
        session = pipeline.Mql5Session(cfg)
        log = w_log_for("forensik")
        if only_new and not neu:
            for r in uebernommen:
                r.urteil = (r.urteil or "") + " | bereits bewertet — unverändert übernommen"
                results.append(r)
            control["new_ids"] = []
            log(f"Alle {n_export} Kandidaten sind bereits bewertet — "
                "nichts neu von MQL5 geladen.")
            w_step("forensik", "complete", done=n_export,
                   detail=f"Alle {n_export} Signale bereits bewertet — unverändert übernommen")
            return
        if w_skip_if_stopped("forensik"):
            return
        if not session.has_credentials:
            log("Kein MQL5-Login — nur Kennzahlen möglich, Trade-Exporte entfallen "
                "(Vorprüfung). Login unter Einstellungen ergänzen.")
        else:
            w_step("forensik", detail="MQL5-Anmeldung prüfen …")
            try:
                from mqlkiscanner.mql5.browser_session import ensure_mql5_cookies
                if not ensure_mql5_cookies(cfg, session, log=log):
                    raise RuntimeError(
                        "Login über Browser nicht bestätigt — Zugangsdaten unter "
                        "Einstellungen prüfen.")
            except Exception as exc:
                w_step("forensik", "error", total=n_export,
                       detail=f"MQL5-Login fehlgeschlagen: {exc}")
                return
        w_step("forensik", "running", total=n_export,
               detail=("Nur neue Signale laden und prüfen …" if only_new
                       else "Handelsdaten laden, speichern und prüfen …"))
        stopped_early = False
        stop_gefordert = False
        new_ids: list[int] = []
        if only_new:
            log(f"Nur-neue-Modus: {len(neu)} neue Signale, "
                f"{len(uebernommen)} bereits bewertet (werden übernommen).")
        for i, candidate in enumerate(neu):
            if control.get("stop"):
                log("Stop angefordert — verbleibende Signale werden nicht mehr geladen.")
                stop_gefordert = True
                break
            w_step("forensik", done=i,
                   detail=f"Signal {i + 1}/{len(neu)}: {candidate.get('name')} #{candidate['id']}")
            try:
                result = pipe.analyze_candidate(
                    session, candidate, log, should_stop=lambda: bool(control.get("stop")))
                results.append(result)
                new_ids.append(result.id)
                if result.persisted_this_run:
                    control["refreshed_ids"].append(result.id)
            except pipeline.Mql5HardStopError as exc:
                if getattr(exc, "result", None) is not None:
                    results.append(exc.result)
                    if exc.result.persisted_this_run:
                        control["refreshed_ids"].append(exc.result.id)
                log(str(exc))
                skipped = len(neu) - (i + 1)
                if skipped > 0:
                    log(f"Fail-Fast: {skipped} weitere Signale nicht mehr von MQL5 geholt.")
                stopped_early = True
                w_step("forensik", done=i + 1)
                break
            w_step("forensik", done=i + 1)
        for r in uebernommen:
            r.urteil = (r.urteil or "") + " | bereits bewertet — unverändert übernommen"
            results.append(r)
        control["new_ids"] = new_ids
        entschieden, vorpruefung, probleme = _station_kennzahlen(results)
        zusatz = f" · {len(uebernommen)} übernommen" if uebernommen else ""
        if stopped_early:
            w_step("forensik", "warning", done=n_export,
                   detail=(f"Abbruch zum Account-Schutz · {entschieden} geprüft · "
                           f"{vorpruefung} Vorprüfung · {probleme} Probleme{zusatz}"))
        elif stop_gefordert:
            w_step("forensik", "warning", done=n_export,
                   detail=(f"Abbruch per Stop-Button · {entschieden} geprüft · "
                           f"{vorpruefung} Vorprüfung · {probleme} Probleme{zusatz}"))
        else:
            w_step(
                "forensik", done=n_export,
                status="complete" if entschieden == len(results) else "error" if probleme == len(results) else "warning",
                detail=(f"{entschieden} gründlich geprüft · {vorpruefung} nur Vorprüfung · "
                        f"{probleme} mit Problemen{zusatz}"),
            )

    def w_run_llm(targets: list[pipeline.ScanResult], cfg) -> None:
        if w_skip_if_stopped("llm"):
            return
        kandidaten = [r for r in targets if r.forensik_vorhanden and not r.fehler
                      and getattr(r, "source_kind", "live") == "live"]
        neu_erstellen = bool(cfg.get("berichte_neu"))
        # Berichte sind in der DB gespeichert — Signale mit vorhandenem
        # Gesamtbericht überspringen und die gespeicherten Texte ins Ergebnis
        # laden, statt alles neu zu erzeugen (Token-/Zeitersparnis).
        try:
            db.init_db()
        except Exception:
            pass
        uebersprungen: list[pipeline.ScanResult] = []
        jobs = kandidaten
        if kandidaten and not neu_erstellen:
            jobs = []
            for r in kandidaten:
                if not pipeline.restore_current_reports(r, cfg):
                    jobs.append(r)
                    continue
                uebersprungen.append(r)
        total = 3 * len(jobs)
        if uebersprungen:
            namen = ", ".join(f"#{r.id} {r.name}" for r in uebersprungen[:8])
            if len(uebersprungen) > 8:
                namen += f" … (+{len(uebersprungen) - 8})"
            logs.setdefault("llm", []).append(_stamped(
                f"{len(uebersprungen)} Signale mit vorhandenem Bericht übersprungen "
                f"(aus der Datenbank geladen): {namen}"))
        if not pipe.llm.has_key or not total:
            if not jobs and uebersprungen:
                w_step("llm", "complete", done=0, total=0,
                       detail=(f"Alle {len(uebersprungen)} Signale haben bereits Berichte — "
                               "aus der Datenbank geladen, nichts neu erzeugt"))
                return
            reason = "Kein KI-Key hinterlegt" if not pipe.llm.has_key else "Keine geeigneten Prüfergebnisse"
            logs["llm"] = logs.get("llm", []) + [_stamped(reason)]
            w_step("llm", "skipped", detail=reason, total=total)
            return
        w_step("llm", "running", total=total, signal_current=0,
               signal_total=len(jobs), detail="Trade-Analyse wird vorbereitet")

        def w_llm_progress(done: int, prompt_total: int, text: str) -> None:
            values = {"done": done, "total": prompt_total, "detail": text}
            prefix = text.partition(" · ")[0]
            if prefix.startswith("Signal ") and "/" in prefix:
                current, signal_total = prefix.removeprefix("Signal ").split("/", 1)
                if current.isdigit() and signal_total.isdigit():
                    values.update(signal_current=int(current),
                                  signal_total=int(signal_total))
            w_step("llm", **values)

        summary = pipe.run_llm(
            jobs, w_log_for("llm"),
            on_progress=w_llm_progress,
            should_stop=lambda: bool(control.get("stop")),
        )
        control["refreshed_ids"] = list(dict.fromkeys(
            [*control["refreshed_ids"], *summary.get("updated_ids", [])]))
        completed, total = summary["completed"], summary["total"]
        failed, skipped = summary["failed"], summary["skipped"]
        signals_bearbeitet = workflow["steps"]["llm"].get("signal_current", 0)
        if (summary.get("reason") or "").startswith("Abbruch"):
            state = "warning"
        else:
            state = "complete" if completed == total else "warning" if completed else "error"
        detail = (
            f"{signals_bearbeitet}/{len(jobs)} Signale bearbeitet · "
            f"{completed}/{total} Berichte gespeichert · {failed} fehlgeschlagen · "
            f"{skipped} nicht ausgeführt · {pipe.llm.usage.total_tokens:,} Tokens"
        )
        if uebersprungen:
            detail += f" · {len(uebersprungen)} übersprungen (Bericht vorhanden)"
        if summary["reason"]:
            detail += f". {summary['reason']}"
        w_step("llm", state, done=completed, total=total, detail=detail)

    def w_run_portfolio(alle: list[pipeline.ScanResult], cfg) -> None:
        if w_skip_if_stopped("portfolio"):
            return
        alle = [r for r in alle if getattr(r, "source_kind", "live") == "live"]
        if not pipe.llm.has_key:
            logs["portfolio"] = [_stamped("Kein KI-Key hinterlegt")]
            w_step("portfolio", "skipped", detail="Kein KI-Key hinterlegt")
            return
        if not any(r.forensik_vorhanden and not r.fehler for r in alle):
            w_step("portfolio", "skipped", detail="Keine geeigneten Prüfergebnisse")
            return
        w_step("portfolio", "running", total=1,
               detail="Alle Berichte werden für die Portfolio-Analyse zusammengefasst …")
        summary = pipe.run_portfolio(
            alle, w_log_for("portfolio"),
            on_progress=lambda done, total, text: w_step("portfolio", done=done, total=total, detail=text),
            should_stop=lambda: bool(control.get("stop")),
        )
        control["portfolio"] = dict(summary)
        if summary.get("text"):
            control["portfolio_bericht"] = summary["text"]
            issue = summary.get("storage_error") or summary.get("reason")
            w_step("portfolio", "warning" if issue else "complete", done=1,
                   detail=(f"Portfolio-Vorschlag erstellt · {summary.get('zeichen', 0):,} Zeichen · "
                           f"{summary.get('tokens', 0):,} Tokens gesamt"
                           + (f" · Speicher-/Laufhinweis: {issue}" if issue else "")))
        elif "Stop" in (summary.get("reason") or ""):
            w_step("portfolio", "warning", detail="Abbruch per Stop-Button")
        else:
            w_step("portfolio", "error",
                   detail=summary.get("reason") or "Kein Portfolio-Bericht erstellt")

    def _worker() -> None:
        current_step = {
            "llm": "llm", "local": "forensik", "step_listen": "listen",
            "step_kandidaten": "kandidaten", "step_forensik": "forensik",
            "step_llm": "llm", "step_portfolio": "portfolio",
        }.get(mode, "listen")
        try:
            try:
                if mode in ("local", "llm", "step_llm", "step_forensik", "step_kandidaten",
                            "step_portfolio"):
                    for sid in ("listen", "kandidaten"):
                        if mode in ("local", "llm", "step_portfolio") or (
                                sid == "listen" and mode in ("step_kandidaten", "step_forensik")
                                and not signals_vorhanden):
                            w_step(sid, "skipped", detail="Vorhandene Daten verwenden")
                if mode == "local":
                    w_step("llm", "skipped", detail="Lokaler Lauf ohne neuen KI-Aufruf")
                    w_step("portfolio", "skipped", detail="Lokaler Lauf ohne neuen KI-Aufruf")
                    files = sorted(config.RAW_DIR.glob("*.csv")) + sorted(config.RAW_DIR.glob("*.json"))
                    if not files:
                        w_step("forensik", "skipped", detail="Keine Testdateien in data/raw vorhanden")
                    else:
                        log = w_log_for("forensik")
                        w_step("forensik", "running", total=len(files),
                               detail="Lokale Testdateien werden geprüft")
                        stopped = False
                        for i, file in enumerate(files):
                            if control.get("stop"):
                                stopped = True
                                log("Stop angefordert — verbleibende Testdateien werden nicht geprüft.")
                                break
                            w_step("forensik", detail=f"Datei {i + 1}/{len(files)}: {file.name}", done=i)
                            rows = pipeline.ScanPipeline.analyze_local_files([str(file)], run_config)
                            results.extend(rows)
                            log(f"{file.name}: " + ("Fehler" if any(r.fehler for r in rows) else "analysiert"))
                            w_step("forensik", done=i + 1)
                        good = sum(r.forensik_vorhanden and not r.fehler for r in results)
                        bad = len(results) - good
                        w_step(
                            "forensik",
                            "warning" if stopped else "complete" if not bad else "warning" if good else "error",
                            detail=(f"{good} Dateien geprüft · {bad} mit Problemen"
                                    + (" · Abbruch per Stop-Button" if stopped else "")),
                        )
                elif mode == "llm":
                    w_step("forensik", "skipped", detail="Vorliegende Prüfergebnisse verwenden")
                    w_run_llm(results, run_config)
                    current_step = "portfolio"
                    w_run_portfolio(results, run_config)
                elif mode == "step_listen":
                    w_run_listen(run_config)
                elif mode == "step_kandidaten":
                    if not signals_vorhanden:
                        w_step("kandidaten", "skipped", detail="Erst Station 1 starten (Signale laden)")
                    else:
                        w_step("listen", "complete", detail=f"{len(signals_vorhanden)} Signale aus Station 1 vorhanden")
                        w_run_kandidaten(signals_vorhanden, run_config)
                elif mode == "step_forensik":
                    if not candidates_vorhanden:
                        w_step("forensik", "skipped", detail="Erst Station 2 starten (Auswahl erzeugen)")
                    else:
                        w_step("kandidaten", "complete",
                               detail=f"{len(candidates_vorhanden)} Signale aus Station 2 vorhanden")
                        w_run_forensik(candidates_vorhanden, run_config)
                elif mode == "step_llm":
                    w_run_llm(results, run_config)
                elif mode == "step_portfolio":
                    w_run_portfolio(results, run_config)
                else:
                    signals = w_run_listen(run_config)
                    current_step = "kandidaten"
                    candidates = w_run_kandidaten(signals, run_config)
                    current_step = "forensik"
                    w_run_forensik(candidates, run_config)
                    ki_an = config.llm_aktiv(run_config)
                    gestoppt = bool(control.get("stop"))
                    if ki_an and not gestoppt:
                        current_step = "llm"
                        w_run_llm(results, run_config)
                        current_step = "portfolio"
                        w_run_portfolio(results, run_config)
                    else:
                        grund = ("Abbruch per Stop-Button vor dieser Station" if gestoppt
                                 else "KI-Berichte für diesen Lauf ausgeschaltet")
                        w_step("llm", "skipped", detail=grund if gestoppt
                               else "KI-Berichte für diesen Lauf ausgeschaltet")
                        w_step("portfolio", "skipped", detail=grund if gestoppt
                               else "Portfolio-Vorschlag für diesen Lauf ausgeschaltet")
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                logs.setdefault(current_step, []).append(_stamped(f"FEHLER: {message}"))
                w_step(current_step, "error", detail=message)
                for sid, *_ in STEPS:
                    if workflow["steps"][sid]["status"] == "pending":
                        w_step(sid, "skipped", detail="Nach vorherigem Fehler nicht ausgeführt")
            workflow["activity"] = "Ergebnisse und Protokoll speichern …"
            try:
                control["last_run_file"] = pipeline.ScanPipeline.save_run(
                    results, logs, portfolio=control.get("portfolio"))
                workflow["saved"] = True
            except Exception as exc:
                workflow.update(status="error", activity=f"Speichern fehlgeschlagen: {exc}")
            states = [s["status"] for s in workflow["steps"].values()]
            if workflow["saved"]:
                final_status = (
                    "error" if "error" in states
                    else "warning" if control.get("stop") or "warning" in states or all(s == "skipped" for s in states)
                    else "complete"
                )
                workflow.update(status=final_status, activity=(
                    "Workflow mit Fehlern beendet. Vorliegende Ergebnisse sind gespeichert."
                    if final_status == "error" else
                    "Workflow beendet. Hinweise prüfen; Ergebnisse sind gespeichert."
                    if final_status == "warning" else
                    f"{len(results)} Ergebnisse gespeichert. "
                    "Unter „Ergebnisse“ können Sie sie vergleichen."
                ))
        except BaseException as exc:  # Worker darf nie laut sterben
            workflow.update(status="error", activity=f"Interner Lauf-Fehler: {exc}")
        finally:
            workflow["finished_at"] = datetime.now().isoformat(timespec="seconds")

    try:
        started = scan_worker.start(_worker, workflow=workflow, control=control,
                                    logs=logs, results=results)
    except Exception as exc:
        workflow.update(status="error", activity=f"Worker konnte nicht gestartet werden: {exc}",
                        finished_at=datetime.now().isoformat(timespec="seconds"))
        control["copied"] = True
        st.session_state.scan_thread = None
        st.session_state.scan_running = None
        st.error(workflow["activity"])
    else:
        if started is None:
            # Zwischen Seitenaufbau und Start kann eine andere Sitzung starten.
            # Atomarer Modul-Guard entscheidet, nicht der Buttonzustand.
            existing = scan_worker.active_run()
            if existing is not None:
                _attach_worker(existing)
            st.rerun()
        _attach_worker(started)

def _problem_art(result) -> tuple[str, str, str]:
    """Kategorie + Handlungs-Hinweis für ein Problem-Ergebnis (Badge-Label, Icon, Hinweis)."""
    text = result.fehler or ""
    if "cross_broker=false" in text:
        return (
            "Broker-Kontrakt nicht verifiziert",
            ":material/fact_check:",
            "Das Instrument wurde erkannt und ein Broker-Suffix bereits entfernt. "
            "Die Sperre betrifft die Kontraktgröße: Bei Öl und einigen CFDs kann "
            "1 Lot je Broker stark unterschiedliche Einheiten bedeuten. Deshalb "
            "darf die Engine den bekannten Wert eines anderen Brokers nicht übernehmen. "
            "Broker/Server und dessen MT5-Kontraktspezifikation prüfen; nur den belegten "
            "Broker anschließend in data/contract_specs.json ergänzen.",
        )
    if "Kontraktspec" in text:
        return (
            "Instrument nicht freigegeben",
            ":material/rule:",
            "Lösbar: Auf der MQL5-Seite des Signals den Broker/Server nachsehen, das "
            "Instrument in data/contract_specs.json für diesen Broker freigeben "
            "(Eintrag „brokers“ ergänzen) und das Signal anschließend neu prüfen.",
        )
    if "Kapitalbasis" in text:
        return (
            "Kapitalbasis unbekannt",
            ":material/account_balance_wallet:",
            "Der Trade-Export beginnt ohne Einzahlung vor dem ersten Trade — z. B. gekürzte "
            "Historie oder eine Auszahlung vor Handelsbeginn. Ohne Startkapital sind Schockanteil "
            "und die 30-%-Schranke nicht berechenbar; das Signal bleibt deshalb bewusst ohne Urteil.",
        )
    if not result.forensik_vorhanden:
        return (
            "Nur Vorprüfung",
            ":material/info:",
            "Es liegen keine vollständigen Handelsdaten vor (z. B. kein MQL5-Login oder kein "
            "Trade-Export verfügbar). Gezählt wird trotzdem, damit nichts unter den Tisch fällt.",
        )
    return (
        "Prüfung abgebrochen",
        ":material/report:",
        "Die Prüfung wurde mit einer Meldung abgebrochen — Details stehen im Text. "
        "Ein erneuter Lauf holt die Daten meist neu.",
    )


@st.dialog("Probleme in diesem Lauf", width="large")
def _probleme_dialog(probleme: list, gesamt: int) -> None:
    """Großes Fenster: jedes Problem verständlich erklärt — was passierte, was tun."""
    st.caption(
        f"{len(probleme)} von {gesamt} Signalen konnten nicht vollständig geprüft werden. "
        "Das sind keine Programmabstürze: Der Scanner bricht die Bewertung eines Signals ab, "
        "wenn sich das Risiko nicht belegen lässt — Risiko vor Ertrag, kein Urteil ohne Datenbasis."
    )
    for r in probleme:
        label, icon, hinweis = _problem_art(r)
        with st.container(border=True):
            kopf = st.container(horizontal=True, vertical_alignment="center")
            kopf.markdown(f"**:material/warning: {r.name}** · #{r.id} · {r.platform}")
            with kopf:
                if r.url:
                    st.markdown(f"[Signal auf MQL5 öffnen]({r.url})")
            st.badge(label, icon=icon, color="orange")
            if r.fehler:
                st.markdown(r.fehler)
            else:
                st.markdown("Keine vollständige forensische Prüfung vorhanden — nur Vorprüfung.")
            st.caption(hinweis)


section_header(
    "Ergebnisse dieses Laufs",
    "Ein abgeschlossener Lauf ist noch keine Empfehlung. Prüfen Sie zuerst die Risikoevidenz.",
    help_key="scan_results",
)
if st.session_state.scan_results:
    results = list(st.session_state.scan_results)
    probleme = [r for r in results if r.fehler or not r.forensik_vorhanden]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Datensätze", len(results), border=True)
    c2.metric("Gründlich geprüft", sum(r.forensik_vorhanden for r in results), border=True)
    c3.metric("Kandidaten", sum(r.ampel == "🟢" for r in results), border=True)
    c4.metric("Probleme", len(probleme), border=True,
              help="Signale, die nicht vollständig geprüft werden konnten — z. B. unbekannte "
                   "Kapitalbasis im Export oder ein nicht freigegebenes Instrument. Das sind "
                   "Analysen-Hinweise, keine Programmfehler. „Probleme ansehen“ erklärt jedes einzelne.")
    if probleme:
        if st.button(f"{len(probleme)} Probleme ansehen — was war los?",
                     key="scan_show_problems", icon=":material/warning:"):
            _probleme_dialog(probleme, len(results))
    st.caption("Tipp: Eine Tabellenzeile auswählen, um die vollständige Risikoprüfung darunter zu öffnen.")
    render_report_panel(results)
    selected = render_results_table(results)
    if selected is not None:
        from mqlkiscanner.app_ui import render_detail
        render_detail(selected)
else:
    with st.container(border=True, key="scan_empty"):
        st.markdown(":material/insights: **Noch keine Ergebnisse.**")
        st.caption(
            "Drücken Sie oben „Starte Workflow“. "
            "Oder unter „Weitere Möglichkeiten“ nur die Testdaten prüfen.")
if st.session_state.get("portfolio_bericht"):
    with st.container(border=True, key="portfolio_panel"):
        st.subheader(":material/pie_chart: Portfolio-Vorschlag (Station 5)")
        st.caption("KI-Empfehlung über alle geprüften Signale: Strategie-Mix, Assets, "
                   "Gewichtung. Keine Anlageberatung.")
        portfolio_result = st.session_state.get("portfolio_result") or {
            "text": st.session_state.portfolio_bericht,
        }
        render_portfolio_pdf_viewer(portfolio_result, key="scan_portfolio_pdf")
        st.markdown(urteile_farbig(st.session_state.portfolio_bericht),
                    unsafe_allow_html=True)
        if issue := portfolio_result.get("storage_error") or portfolio_result.get("reason"):
            st.warning(f"Portfolio-Hinweis: {issue}")
