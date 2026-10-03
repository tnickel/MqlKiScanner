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
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, db, downloader_sync, fix_signale, pipeline, scan_state, scan_worker, secrets_store
from mqlkiscanner.app_ui import (
    render_downloader_docs_panel,
    render_portfolio_pdf_viewer,
    render_report_panel,
    render_results_table,
    render_wechsel_karten,
)
from mqlkiscanner.ui_design import (
    action_button, aktivitaets_html, apply_theme, page_header, section_header,
    urteile_farbig, render_workflow_stepper,
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
    ("downloader", "Abgleich", "sync", "Signale",
     "Abonnenten-Verläufe und Testreport-PDFs aus dem MqlDownloader holen — nie eine Neubewertung"),
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
    if command["mode"] in ("scan", "gelbgruen", "step_listen"):
        st.session_state.scan_signals = []
    if command["mode"] in ("scan", "gelbgruen", "step_listen", "step_kandidaten"):
        # Nachgelagerte Daten gehören zur vorherigen Auswahl. Auch bei einem
        # Fehler im neuen Abruf dürfen sie nicht als neuer Stand weiterlaufen.
        st.session_state.scan_candidates = []
    if command["mode"] == "scan" and command["settings"] and not (
            config.llm_aktiv(command["settings"])):
        workflow["steps"]["llm"].update(status="skipped", detail="KI-Berichte für diesen Lauf ausgeschaltet")
        workflow["steps"]["portfolio"].update(status="skipped", detail="Portfolio-Vorschlag für diesen Lauf ausgeschaltet")
    if command["mode"] in ("scan", "gelbgruen", "step_listen"):
        st.session_state.scan_results = []
        st.session_state.scan_logs = {}
        st.session_state.last_run_file = None
        st.session_state.portfolio_bericht = ""
    if command["mode"] in ("local", "step_kandidaten", "step_forensik"):
        # Eine neue Prüfung ersetzt die vorherige Ergebnismenge dieser Sitzung.
        st.session_state.scan_results = []
        st.session_state.portfolio_bericht = ""
    if command["mode"] in ("scan", "gelbgruen", "local", "step_forensik"):
        st.session_state.scan_new_ids = []

settings = config.load_settings()
running = command is not None or _thread_lebt
hero_banner = Path(__file__).resolve().parents[1] / "assets" / "hero_scan_banner.jpg"
page_header(
    "RISIKOPRÜFUNG",
    "Handelssignale aller Quellen belastbar prüfen",
    "Eine Analyse verbindet Handelsdaten aus allen angeschlossenen Quellen "
    "(MQL5, Pelican, RoboForex, Vantage, Zulu — je nach Konfiguration), "
    "forensische Risikotests und optional KI-Berichte. **Schutz muss belegt "
    "sein; 30 % Drawdown ist die harte Grenze.**",
    image_path=str(hero_banner) if hero_banner.exists() else None,
)
if reattached:
    st.info("Ein Workflow läuft bereits im Hintergrund. Der laufende Prozess wurde "
            "wieder verbunden; Status und Stop-Button steuern denselben Lauf.")
section_header(
    "Analyse starten",
    "Ein Start, sechs nachvollziehbare Stationen, ein gespeicherter Ergebnisstand.",
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


def _station_requested() -> None:
    """Ein Stationsereignis für die Detailansicht vormerken."""
    event = st.session_state.get("scan_station_stepper") or {}
    sid = event.get("station")
    if sid in {step[0] for step in STEPS}:
        st.session_state["_scan_station_dialog"] = sid
        st.rerun("scan_station_dialog_host")


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
            "nr": nr, "sid": sid, "title": title, "status": step["status"],
            "label": STATES[step["status"]][0],
            "meta": step.get("detail") if step["status"] != "pending" else beschreibung,
            "frac": _step_fraction(step) if step["status"] == "running" else None,
            "hint": sid == first_pending and status != "running",
        })
    # Doppelklick meldet die Station direkt an Python. Keine Navigation:
    # Sitzung, Worker und Laufdaten bleiben für die Detailansicht erhalten.
    render_workflow_stepper(
        payload, overall, key="scan_station_stepper",
        on_station_change=_station_requested,
    )
    # Stationsdialoge öffnet ein unabhängiges Fragment. Als Kind dieses
    # Status-Fragments würden sie beim nächsten Tick intern entfernt,
    # obwohl das Fenster sichtbar bleibt und weiter Filterklicks annimmt.

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

    # Festes Aktivitäts-Badge oben rechts: bleibt auch beim Weiterscrollen
    # sichtbar und nennt die laufende Station (Fragment tickt jede Sekunde,
    # also verschwindet das Badge automatisch mit dem Laufende).
    if status == "running" and laufend:
        st.markdown(aktivitaets_html(
            f"Station {laufend[1]}: {laufend[2]} läuft …"), unsafe_allow_html=True)

    # Lauf beendet? Einmal die GANZE Seite neu laden: Ergebnisübernahme
    # (Session) + Endstand (Tabelle, Portfolio) rendern.
    th = st.session_state.scan_thread
    if (th is not None and not th.is_alive()
            and st.session_state.get("_copied_scan_control") is not st.session_state.scan_control):
        st.rerun(scope="app")


has_login = bool(secrets_store.get_secret("mql5_user") and secrets_store.get_secret("mql5_pass"))
has_llm = bool(secrets_store.get_secret("glm_api_key"))
dl_status = downloader_sync.verbindungs_status(timeout=3.0)
with st.container(border=True, key="scan_control_panel"):
    with st.container(horizontal=True, gap="small"):
        st.badge("MQL5 bereit" if has_login else "MQL5-Zugang fehlt",
                 icon=":material/lock:", color="green" if has_login else "orange")
        st.badge("KI-Berichte aktiv" if has_llm else "KI optional",
                 icon=":material/psychology:", color="green" if has_llm else "gray")
        mql_quelle = next((q for q in dl_status.get("quellen", [])
                           if q["kuerzel"] == "mql5"), None)
        if mql_quelle is None:
            st.badge("Downloader nicht konfiguriert", icon=":material/sync:",
                     color="gray")
        else:
            st.badge("Downloader verbunden" if mql_quelle["ok"]
                     else "Downloader offline",
                     icon=":material/sync:" if mql_quelle["ok"]
                     else ":material/sync_disabled:",
                     color="green" if mql_quelle["ok"] else "red")
        for q in dl_status.get("quellen", []):
            if q["kuerzel"] == "mql5":
                continue  # oben als „Downloader" gezeigt
            st.badge(f"{q['name']} verbunden" if q["ok"]
                     else f"{q['name']} offline",
                     icon=":material/sync:" if q["ok"]
                     else ":material/sync_disabled:",
                     color="green" if q["ok"] else "red")
    start_zeile = st.columns([1.15, 1.15, 1], gap="small", vertical_alignment="center")
    with start_zeile[0]:
        start = action_button(
            "Full-Scan",
            key="scan_start",
            help_key="scan_start",
            type="primary",
            icon=":material/play_arrow:",
            disabled=running,
        )
    with start_zeile[1]:
        gelbgruen_start = action_button(
            "Teilscan",
            key="scan_gelbgruen",
            help_key="scan_gelbgruen",
            icon=":material/monitor_heart:",
            disabled=running,
        )
    with start_zeile[2]:
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
            fix_hinweis = fix_signale.fix_ids()
            st.caption(
                "Full-Scan prüft alles; Teilscan nur 🟢/🟡-Signale"
                + (" plus Fix-IDs" if fix_hinweis else "")
                + " mit allen KI-Stufen. Stop jederzeit möglich."
                + (f" Fix gesetzt: {', '.join(f'#{i}' for i in sorted(fix_hinweis))}."
                   if fix_hinweis else ""))

    _live_status()
    st.caption("Doppelklick auf einen Kreis öffnet die Erklärung mit Tabelle.")

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
        _modus_optionen = {"mql5": "MQL5 direkt (Crawler)",
                           "quellen": "Datenquellen (REST)",
                           "beides": "Beides (Vereinigung)"}
        _modus_aktiv = str(settings.get("listen_modus") or "mql5")
        listen_modus = st.selectbox(
            "Signale holen aus",
            options=list(_modus_optionen),
            format_func=_modus_optionen.get,
            index=list(_modus_optionen).index(_modus_aktiv)
            if _modus_aktiv in _modus_optionen else 0,
            key="set_listen_modus", disabled=running,
            help="Datenquellen (REST): Kandidaten und Trades ausschließlich aus den "
                 "im Admin konfigurierten Quellen (doc/20) — kein Kontakt zu mql5.com.")
        pages = st.number_input(
            "Listen-Seiten je MT4/MT5", *config.SCAN_INPUT_BOUNDS["listen_seiten"], value=int(settings["listen_seiten"]),
            key="set_seiten", disabled=running or listen_modus == "quellen")
        top_n = st.number_input(
            "Max. Signale gründlich prüfen (je Quelle)", *config.SCAN_INPUT_BOUNDS["top_n_export"], value=int(settings["top_n_export"]),
            key="set_topn", disabled=running,
            help="Gilt JE Datenquelle: 30 heißt bis zu 30 MQL5- UND 30 "
                 "Pelican-Signale in der Forensik; Fix-IDs kommen immer dazu.")
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
    "listen_modus": str(listen_modus),
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
if start or gelbgruen_start or verify or llm_only:
    st.session_state.scan_command = {
        "mode": "scan" if start else "gelbgruen" if gelbgruen_start
        else "local" if verify else "llm",
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
    if mode == "gelbgruen":
        # Modus-Vertrag (Nutzer-Vorgabe): nur aktuell 🟢/🟡-Signale prüfen und
        # dafür IMMER alle LLM-Stufen neu erzeugen — unabhängig von den
        # Laufzeit-Toggles (nur_neue/berichte_neu/KI-Toggle gelten nicht).
        run_config = {**run_config, "nur_neue": False, "berichte_neu": True,
                      "llm_stufe1": True, "llm_stufe2": True}
    logs = st.session_state.scan_logs
    results = st.session_state.scan_results
    signals_vorhanden = st.session_state.get("scan_signals")
    candidates_vorhanden = st.session_state.get("scan_candidates")
    control = {"stop": False, "portfolio_bericht": "", "portfolio": None, "new_ids": [],
               "signals": signals_vorhanden or [], "candidates": candidates_vorhanden or [],
               "last_run_file": None, "refreshed_ids": [], "copied": False,
               "ampel_wechsel": []}
    st.session_state.scan_control = control
    st.session_state.scan_running = mode if mode not in ("scan",) else "listen"
    pipe = pipeline.ScanPipeline(run_config,
                                 quelle="gelbgruen" if mode == "gelbgruen" else "full")

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
            # Nutzer-Forderung 29.09.: Fehlermeldungen muessen IMMER geloggt
            # werden — die Session-Anzeige verschwindet beim Neustart. Jede
            # Workflow-Zeile (auch mehrzeilige Tracebacks) landet dauerhaft
            # in data/scan_workflow.log.
            try:
                logdatei = config.DATA_DIR / "scan_workflow.log"
                logdatei.parent.mkdir(parents=True, exist_ok=True)
                with logdatei.open("a", encoding="utf-8") as fh:
                    fh.write(_stamped(f"[{sid}] " + message) + "\n")
            except OSError:
                pass  # Log darf den Scan nie blockieren
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
        begruendung: list[dict] = []
        candidates = pipe.build_candidates(signals, w_log_for("kandidaten"),
                                           begruendung=begruendung)
        control["candidates"] = candidates
        control["begruendung"] = begruendung
        w_step("kandidaten", "complete", done=len(signals),
               detail=f"{len(candidates)} passende Signale aus {len(signals)}")
        return candidates

    def w_run_forensik(cands: list[dict], cfg) -> None:
        if w_skip_if_stopped("forensik"):
            return
        log = w_log_for("forensik")
        if mode == "gelbgruen":
            # Modus-Vertrag: nur Signale prüfen, deren aktuelle Bewertung
            # (Datenbank-Stand) 🟢 oder 🟡 ist — alle anderen werden in
            # diesem Lauf nicht beachtet. Bestimmung über results_from_db,
            # damit dieselbe Ampel-Logik wie in der Anzeige entscheidet.
            # Fix-IDs sind zusätzlich IMMER im Scope (Nutzer-Wunsch
            # 28.09.2026: definierte IDs immer scannen).
            alt_ergebnisse = pipeline.results_from_db(cfg)
            ziel_ids = fix_signale.teilscan_ziel_ids(alt_ergebnisse, cfg)
            vorher = len(cands)
            fix_signale.begruende_teilscan_scope(
                control.get("begruendung"), cands, ziel_ids, alt_ergebnisse)
            cands = [c for c in cands if c["id"] in ziel_ids]
            # Quelle offline (z. B. PelicanMonitor aus): deren 🟢/🟡 aus der
            # DB ergänzen — Forensik aus den Cache-Artefakten (Nutzer-Fall
            # 02.10.: 12 pelik-🟡 wurden still übersprungen).
            ergaenzungen = fix_signale.teilscan_ergaenze_aus_db(
                ziel_ids, {c["id"] for c in cands}, cfg,
                begruendung=control.get("begruendung"))
            if ergaenzungen:
                cands.extend(ergaenzungen)
                log(f"+{len(ergaenzungen)} 🟢/🟡 aus der DB ergänzt "
                    "(Quelle offline — Forensik aus Cache-Artefakten).")
            log(f"Teilscan: {len(cands)} von {vorher} Kandidaten sind "
                "aktuell 🟢/🟡 oder Fix-ID — nur diese werden geprüft.")
            if not cands:
                w_step("forensik", "skipped",
                       detail="Keine 🟢/🟡- oder Fix-Signale in Auswahl und Katalog — nichts zu prüfen")
                return
        # Fix-Kandidaten vorne (die Grenze trifft sie nie); danach JE
        # Quelle die top_n abonnentenstärksten Kandidaten (Nutzer-Wunsch
        # 29.09.: „30 von jedem" — MQL5 und Pelican konkurrieren nicht
        # mehr um dieselben Slots).
        _begr = control.get("begruendung") or []
        scope, export_infos = fix_signale.waehle_fuer_export(
            cands, cfg["top_n_export"], cfg, begruendung=_begr,
            modus=("gelbgruen" if mode == "gelbgruen" else "full"))
        _begruendung_speichern(_begr, cfg["top_n_export"],
                               modus=("Teilscan" if mode == "gelbgruen" else "Full-Scan"))
        n_export = len(scope)
        log("Auswahl je Quelle: " + " · ".join(
            f"{i['quelle']}: {i['genommen']}/{i['angeboten']}" for i in export_infos)
            + f" — gesamt {n_export} für die Forensik.")
        if not n_export:
            w_step("forensik", "skipped", detail="Keine passenden Signale nach der Auswahl")
            return
        only_new = bool(cfg.get("nur_neue"))
        alt: dict[int, pipeline.ScanResult] = {}
        if only_new:
            alt = {r.id: r for r in pipeline.results_from_db(cfg) if r.forensik_vorhanden
                   and getattr(r, "source_kind", "live") == "live"}
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
        # B7 (Lauf-Review 02.10.): Login nur, wenn MQL5-DIREKT-Kandidaten im
        # Scope sind (F6-Logik des autonomen Launchers) — reine Quellen-Läufe
        # brauchen kein mql5.com und dürfen an einem Login-Ausfall nicht
        # scheitern.
        hat_mql5_direkt = any(not c.get("quelle_kuerzel") for c in cands)
        if not hat_mql5_direkt:
            log("Keine MQL5-Direkt-Kandidaten im Scope — MQL5-Login nicht "
                "erforderlich (nur Datenquellen werden geprüft).")
        elif not session.has_credentials:
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
        try:
            # L12 (Review-Handoff 29.09.): jede unerwartete Exception
            # im Loop uebersprang kursdaten_beenden() -> MT5-Leak.
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
                    _merke_wechsel(result)
                    if result.persisted_this_run:
                        control["refreshed_ids"].append(result.id)
                except pipeline.Mql5HardStopError as exc:
                    if getattr(exc, "result", None) is not None:
                        results.append(exc.result)
                        _merke_wechsel(exc.result)
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
        finally:
            pipe.kursdaten_beenden()  # MT5-Terminal der Kursdaten nach dem Lauf schließen
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

    def _merke_wechsel(r) -> None:
        """Wechsel-Ereignis des Laufs einsammeln (Protokoll liegt zusätzlich in der DB)."""
        ereignis = getattr(r, "ampel_wechsel", None)
        if ereignis:
            control["ampel_wechsel"].append(ereignis)

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

    def w_run_downloader(alle: list[pipeline.ScanResult], cfg) -> None:
        """Station 6: Abgleich mit dem MqlDownloader (best-effort, nie Neubewertung)."""
        if w_skip_if_stopped("downloader"):
            return
        ziele: list[tuple[int, str]] = []
        gesehen: set[int] = set()
        for r in alle:
            if getattr(r, "source_kind", "live") != "live" or not r.id or r.id in gesehen:
                continue
            gesehen.add(r.id)
            ziele.append((r.id, getattr(r, "platform", "") or ""))
        if not downloader_sync.konfiguriert():
            w_step("downloader", "skipped",
                   detail="MqlDownloader nicht konfiguriert (Admin → MqlDownloader)")
            return
        if not ziele:
            w_step("downloader", "skipped", detail="Keine Live-Signale im Lauf")
            return
        log = w_log_for("downloader")
        downloader_sync.warne_url_divergenz(log)  # B9: Setting vs. Datenquelle
        w_step("downloader", "running", total=len(ziele),
               detail="Abonnenten-Verläufe und Testreport-PDFs werden geholt …")
        summary = downloader_sync.sync_many(
            ziele,
            progress=lambda done, total_, sid: w_step(
                "downloader", done=done, total=total_,
                detail=f"Signal {done}/{total_} (#{sid}) wird abgeglichen …"))
        if summary["abgebrochen"]:
            log("Abbruch: " + summary["abgebrochen"])
            w_step("downloader", "warning", done=len(ziele),
                   detail=f"Abgleich abgebrochen — Geladenes bleibt gespeichert. "
                          f"{summary['abgebrochen'][:160]}")
            return
        for fehler in summary["fehler"]:
            log("Hinweis: " + fehler)
        log(f"{summary['signale']} Signale abgeglichen · {summary['verlaufspunkte']} "
            f"Verlaufspunkte gesichert · {summary['neue_pdfs']} neue Testreport-PDFs.")
        w_step("downloader", "warning" if summary["fehler"] else "complete", done=len(ziele),
               detail=(f"{summary['signale']} Signale · {summary['verlaufspunkte']} "
                       f"Verlaufspunkte gesichert · {summary['neue_pdfs']} neue PDFs"
                       + (f" · {len(summary['fehler'])} Hinweise" if summary["fehler"] else "")))

    def _worker() -> None:
        current_step = {
            "llm": "llm", "local": "forensik", "step_listen": "listen",
            "step_kandidaten": "kandidaten", "step_forensik": "forensik",
            "step_llm": "llm", "step_portfolio": "portfolio",
            "step_downloader": "downloader",
        }.get(mode, "listen")
        try:
            try:
                if mode in ("local", "llm", "step_llm", "step_forensik", "step_kandidaten",
                            "step_portfolio", "step_downloader"):
                    for sid in ("listen", "kandidaten"):
                        if mode in ("local", "llm", "step_portfolio", "step_downloader") or (
                                sid == "listen" and mode in ("step_kandidaten", "step_forensik")
                                and not signals_vorhanden):
                            w_step(sid, "skipped", detail="Vorhandene Daten verwenden")
                if mode == "local":
                    w_step("llm", "skipped", detail="Lokaler Lauf ohne neuen KI-Aufruf")
                    w_step("portfolio", "skipped", detail="Lokaler Lauf ohne neuen KI-Aufruf")
                    w_step("downloader", "skipped", detail="Lokaler Lauf ohne Downloader-Abgleich")
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
                elif mode == "step_downloader":
                    # B2 (Lauf-Review 02.10.): „Nur Station 6" darf KEINEN
                    # kompletten Scan starten (vorher fiel der Modus durch
                    # alle Zweige und lief Crawl + Forensik + KI). Der
                    # Abgleich nutzt die Ergebnisse der laufenden Sitzung
                    # bzw. des letzten Laufs — ohne neue Prüfungen.
                    if not results:
                        w_step("downloader", "skipped",
                               detail="Keine Ergebnisse in dieser Sitzung — "
                                      "erst scannen (der Abgleich spiegelt "
                                      "Lauf-Signale)")
                    else:
                        w_run_downloader(results, run_config)
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
                    current_step = "downloader"
                    w_run_downloader(results, run_config)
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
                                    logs=logs, results=results,
                                    lock_basis=config.DATA_DIR)
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


# ---------------------------------------------------------- Stations-Helfer
# Nutzer-Wunsch 02.10.2026: JEDE Filter-Entscheidung der Pipeline je Signal
# nachvollziehbar — Vollliste je Station, Quelle, Link zum Ursprungssignal,
# Filterleiste (Anzeige/Quelle/Suche), Default „beides anzeigen“.

_STATUS_ICON = {
    "AUSGEWAEHLT": "✅ In der Forensik",
    "FIX": "📌 Fix-ID (immer scannen)",
    "NICHT_IM_SCOPE": "⏭️ Nicht im Teilscan-Scope",
    "OHNE_SLOT": "❌ Kein Forensik-Slot",
    "AUSGESCHLOSSEN": "⛔ Ausschlussliste",
    "DRAUSSEN": "🚫 Vorfilter raus",
    "KANDIDAT": "➡️ Kandidat",
}
_GEWAHLT_STATUS = {"AUSGEWAEHLT", "FIX"}


def _signal_link(e: dict) -> str:
    """Echte Signal-URL oder leer. Pelican liefert nur den Plattform-Root —
    das ist kein Signal-Link und wird nicht ausgegeben (keine URLs erfinden).
    Vantage liefert discoverDetail-URLs je Strategie, MQL5 /signals/{id}."""
    url = str(e.get("url") or "").strip()
    quelle = str(e.get("quelle") or e.get("quelle_kuerzel") or "mql5")
    sid = e.get("id")
    if not url and quelle == "mql5" and sid is not None:
        url = f"https://www.mql5.com/en/signals/{sid}"
    if "/signals/" in url or "strategyId=" in url:
        return url
    return ""


def _filterleiste(rows: list[dict], key_suffix: str,
                  label_gewaehlt: str = "Nur gewählt",
                  label_raus: str = "Nur nicht gewählt") -> list[dict]:
    """Filterleiste über den Signaltabellen: Anzeige (Default: alle),
    Quelle (Default: alle) und Freitextsuche nach Name oder ID."""
    c1, c2, c3 = st.columns([1.5, 1.2, 1.8])
    hat_status = any(r.get("_gewaehlt") is not None for r in rows)
    if hat_status:
        anzeige = c1.segmented_control(
            "Anzeige", ["Alle", label_gewaehlt, label_raus],
            default="Alle", key=f"_flt_anzeige_{key_suffix}")
    else:
        anzeige = "Alle"
        c1.caption("Anzeige: alle (keine Auswahlentscheidung in dieser Stufe)")
    quellen = sorted({str(r.get("Quelle")) for r in rows if r.get("Quelle")})
    qsel = c2.multiselect("Quelle", quellen, default=quellen,
                          key=f"_flt_quelle_{key_suffix}",
                          help="Herkunft der Signale — MQL5-Direkt oder eine "
                               "der angeschlossenen Datenquellen (REST).")
    suche = (c3.text_input("Suchen (Name oder ID)",
                           key=f"_flt_suche_{key_suffix}") or "").strip().lower()
    out = rows
    if hat_status and anzeige == label_gewaehlt:
        out = [r for r in out if r["_gewaehlt"]]
    elif hat_status and anzeige == label_raus:
        out = [r for r in out if r["_gewaehlt"] is False]
    erlaubt = set(qsel)
    out = [r for r in out if str(r.get("Quelle")) in erlaubt]
    if suche:
        out = [r for r in out if suche in str(r.get("Signal", "")).lower()
               or suche in str(r.get("ID", "")).lower()]
    return out


def _link_spalte() -> object:
    return st.column_config.LinkColumn("Ursprung", display_text="↗ öffnen")


def _ohne_intern(rows: list[dict]) -> list[dict]:
    """Interne Filter-Marker (_gewaehlt) nicht als Spalte anzeigen."""
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def _begruendung_zeilen(eintraege: list[dict]) -> list[dict]:
    """Begründungs-Einträge (auswahl_begruendung.json) in Tabellen-Zeilen."""
    rows = []
    for e in eintraege:
        status = str(e.get("status") or "KANDIDAT")
        rows.append({
            "Status": _STATUS_ICON.get(status, status),
            "Signal": e.get("name") or f"#{e.get('id')}",
            "ID": e.get("id"),
            "Quelle": e.get("quelle") or "mql5",
            "Wochen": e.get("wochen"),
            "Abos": e.get("abonnenten"),
            "Grund": e.get("grund") or "",
            "Link": _signal_link(e),
            "_gewaehlt": status in _GEWAHLT_STATUS,
        })
    return rows


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


@st.dialog("📡 Station 1 · Signale holen — was kam rein?", width="large")
def _dialog_listen() -> None:
    """Signale je Quelle: was der Crawl geliefert hat und was fehlte."""
    import pandas as pd
    from collections import Counter as _C
    st.markdown("**Was passiert hier?** Der Scanner lädt die Signalkataloge aus den "
                "eingestellten Quellen. Bei MQL5 werden Top-Listen und fehlende Fix-IDs "
                "abgerufen, bei REST-Quellen deren Kataloge. Die Handelsdaten für die "
                "Risikoprüfung folgen in Station 3. Ein geladenes Signal ist noch keine Empfehlung.")
    datei = config.DATA_DIR / "auswahl_begruendung.json"
    daten = {}
    if datei.exists():
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            st.warning(f"Die gespeicherte Auswahl kann nicht gelesen werden: {exc}")
    # B13 (Lauf-Review 02.10.): Während eines laufenden Workflows hat
    # Station 1 die FRISCHE Liste in control['signals'] geschrieben — die
    # alte Session-Liste (scan_signals) würde den vorigen Stand zeigen.
    # Lauf-Daten gehen vor, danach Session, dann gespeicherter Lauf.
    eintraege = list((st.session_state.get("scan_control") or {}).get("signals")
                     or st.session_state.get("scan_signals") or [])
    sitzungsdaten = bool(eintraege)
    if eintraege:
        st.caption("Signale aus dem Lauf in dieser Sitzung.")
    else:
        eintraege = daten.get("eintraege") or []
        if daten:
            st.caption(f"Gespeicherter Lauf: {daten.get('zeitstempel', '?')}.")
        else:
            st.info("Noch keine Signale geladen. Die Tabelle zeigt die konfigurierten "
                    "Quellen; Signalzahlen erscheinen nach Station 1.")
    def _herkunft(e):
        kuerzel = e.get("quelle_kuerzel") or e.get("quelle") or "mql5"
        if sitzungsdaten:
            zugriff = "REST" if e.get("quelle_kuerzel") or e.get("quelle_id") or e.get("quelle") else "MQL5-Direkt"
        else:
            zugriff = "REST" if kuerzel != "mql5" else "Nicht aufgezeichnet"
        return kuerzel, zugriff

    quellen = _C(_herkunft(e) for e in eintraege)
    konfigurierte = {q["kuerzel"]: q for q in db.list_quellen()}
    modus = str(settings.get("listen_modus") or "mql5").strip().lower()
    mql5_nicht_getrennt = bool(quellen.get(("mql5", "Nicht aufgezeichnet")))
    rows = [{"Quelle": "MQL5-Direkt", "Kürzel": "mql5", "Zugriff": "MQL5-Direkt",
             "Im Scan aktiv": "Ja" if modus in ("mql5", "beides") else "Nein",
             "Geladene Signale": (quellen.get(("mql5", "MQL5-Direkt"), 0)
                                  if eintraege and not mql5_nicht_getrennt else None),
             "Letzter Verbindungstest": "—", "Geprüft am": "—"}]
    rest_kuerzel = {k for k, zugriff in quellen if zugriff == "REST"}
    for kuerzel in sorted(set(konfigurierte) | rest_kuerzel):
        q = konfigurierte.get(kuerzel) or {}
        pruefung = q.get("letzte_pruefung") or {}
        im_scan = bool(q.get("aktiv")) and modus in ("quellen", "beides")
        zahl = quellen.get((kuerzel, "REST"), 0) if eintraege else None
        if kuerzel == "mql5" and mql5_nicht_getrennt:
            zahl = None
        rows.append({"Quelle": q.get("name") or kuerzel, "Kürzel": kuerzel,
                     "Zugriff": "REST",
                     "Im Scan aktiv": "Ja" if im_scan else "Nein",
                     "Geladene Signale": zahl,
                     "Letzter Verbindungstest": {
                         "ok": "Erreichbar", "eingeschraenkt": "Eingeschränkt",
                         "fehler": "Nicht erreichbar",
                     }.get(pruefung.get("status"), pruefung.get("text") or "Nicht geprüft"),
                     "Geprüft am": pruefung.get("geprueft") or "—"})
    quellen_tabelle = pd.DataFrame(rows, columns=["Quelle", "Kürzel", "Zugriff", "Im Scan aktiv",
                 "Geladene Signale", "Letzter Verbindungstest", "Geprüft am"])
    quellen_tabelle["Geladene Signale"] = pd.array(quellen_tabelle["Geladene Signale"], dtype="Int64")
    st.dataframe(quellen_tabelle, width="stretch", hide_index=True)
    st.caption("Die Tabelle verwendet gespeicherte Verbindungstests. "
               "Aktivierung zeigt die aktuellen Einstellungen.")
    if mql5_nicht_getrennt:
        st.caption(f"Die gespeicherte Auswahl enthält {quellen[('mql5', 'Nicht aufgezeichnet')]} "
                   "Signale mit Kürzel mql5. MQL5-Direkt und MqlDownloader wurden dort "
                   "nicht getrennt aufgezeichnet; ihre einzelnen Signalzahlen sind unbekannt.")
    if eintraege:
        zeilen = []
        for e in eintraege:
            kuerzel, zugriff = _herkunft(e)
            zeilen.append({
                "Signal": e.get("name", ""), "ID": e.get("id"),
                "Quelle": kuerzel, "Zugriff": zugriff,
                "Wochen": e.get("wochen"), "Abos": e.get("abonnenten"),
                "Link": _signal_link(e)})
        st.caption(f"**Alle {len(zeilen)} geladenen Signale** — Herkunft je "
                   "Signal; über die Filter lässt sich je Quelle einschränken.")
        zeilen = _filterleiste(zeilen, "listen")
        st.dataframe(zeilen, width="stretch", hide_index=True,
                     column_config={"Link": _link_spalte()})
        st.caption("Pelican-Signale haben keinen klickbaren Ursprungs-Link — "
                   "die Plattform liefert keine Signal-URL (nur die Startseite); "
                   "MQL5- und Vantage-Signale verlinken auf ihre Detailseite.")
    st.caption("Nicht erreichbare Kataloge stehen im Meldungs-Feed. Im Teilscan "
               "können gespeicherte 🟢/🟡-Signale aus der DB ergänzt werden.")


@st.dialog("🔍 Station 2 · Auswahl — warum jedes Signal drin oder draußen ist", width="large")
def _dialog_auswahl() -> None:
    """EINE scrollbare Tabelle: ALLE Signale des Laufs mit Grund je Signal,
    Filterleiste (Anzeige/Quelle/Suche) — Nutzer-Wunsch 02.10."""
    st.markdown("**Was passiert hier?** Drei Filter hintereinander: "
                "(1) der **Vorfilter** prüft Mindestalter und Mindest-"
                "Abonnentenzahl, (2) der **Scan-Modus** entscheidet den Scope — "
                "im Teilscan werden nur aktuell 🟢/🟡 laut Datenbank plus "
                "Fix-IDs geprüft, im Full-Scan alle Kandidaten — und (3) die "
                "**Slots**: je Quelle kommen die abonnentenstärksten Kandidaten "
                "in die Forensik (Fix-IDs umgehen alles und belegen keinen "
                "Slot). Für jedes Signal steht der Grund in der Tabelle.")
    datei = config.DATA_DIR / "auswahl_begruendung.json"
    if not datei.exists():
        st.info("Noch keine Auswahl aufgezeichnet. Nach dem Scan zeigt die "
                "Tabelle für jedes Signal, warum es ausgewählt oder "
                "aussortiert wurde.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.warning(f"Die gespeicherte Auswahl kann nicht gelesen werden: {exc}")
        return
    eintraege = daten.get("eintraege") or []
    if not eintraege:
        st.info("Die gespeicherte Auswahl ist leer.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    # Filter-Kette als Zahlen — jede Zeile der Tabelle erklärt den Sprung.
    n_gesamt = len(eintraege)
    n_draussen = sum(1 for e in eintraege if e.get("status") == "DRAUSSEN")
    n_kandidaten = sum(1 for e in eintraege
                       if e.get("status") != "DRAUSSEN")
    n_gewaehlt = sum(1 for e in eintraege
                     if e.get("status") in _GEWAHLT_STATUS)
    modus = daten.get("modus") or "—"
    st.caption(f"Stand: {daten.get('zeitstempel', '?')} · Modus: {modus} · "
               f"mindestens {settings['min_wochen']} Wochen, "
               f"{settings['min_abonnenten']} Abonnenten, "
               f"Top {daten.get('top_n_export', '?')} je Quelle. "
               "Abonnentenzahl ist kein Qualitätsnachweis.")
    st.markdown(f"**Filter-Kette:** {n_gesamt} Signale geladen "
                f"→ {n_draussen} fielen durch den **Vorfilter** "
                f"→ {n_kandidaten} Kandidaten → {n_gewaehlt} kamen in die "
                "**Forensik** (Modus-Scope + Slots).")
    zeilen = _begruendung_zeilen(eintraege)
    zeilen = _filterleiste(zeilen, "auswahl")
    st.caption(f"Angezeigt: {len(zeilen)} von {n_gesamt} Signalen.")
    st.dataframe(_ohne_intern(zeilen), width="stretch", hide_index=True,
                 column_config={"Link": _link_spalte()})
    st.caption("Status-Bedeutung: ✅ geprüft · 📌 Fix-ID (immer scannen) · "
               "⏭️ im Teilscan nicht dran (letztes Urteil nicht 🟢/🟡) · "
               "❌ Kandidat, aber hinter den Top-N-Slots je Quelle · "
               "⛔ Ausschlussliste (kuratiert, belegt keinen Slot) · "
               "🚫 Vorfilter (Alter/Abonnenten). Pelican-Signale ohne "
               "Ursprungs-Link: Plattform liefert keine Signal-URL.")


@st.dialog("🔬 Station 3 · Prüfen & speichern — Forensik-Ergebnisse", width="large")
def _dialog_forensik() -> None:
    """Kombinierte Sicht: alle Kandidaten des Laufs — wer geprüft wurde
    (mit Ergebnis) und wer nicht (mit Grund), Filterleiste oben."""
    st.markdown("**Was passiert hier?** Für die ausgewählten Signale lädt der "
                "Scanner Handelsdaten (Export bzw. Quellen-Artefakte) und "
                "prüft Martingale, gleichzeitig offene Positionen, Exposure, "
                "Stop-Signaturen und Drawdown. Der Code berechnet Kennzahlen, "
                f"Ampel und Score. Die Drawdown-Schranke liegt bei "
                f"{settings.get('schranke_eq_dd_pct', 30):g} %. "
                "Fehlender Stop-Nachweis ist neutral.")
    results = list(st.session_state.get("scan_results") or [])
    aus_db = False
    if not results:
        # Ohne Sitzungs-Daten den letzten DB-Stand zeigen — klar markiert.
        try:
            results = list(pipeline.results_from_db(settings))
            aus_db = bool(results)
        except Exception:
            results = []
    if aus_db:
        st.caption("Kein Lauf in dieser Sitzung — angezeigt ist der letzte "
                   "gespeicherte Datenbank-Stand (kann älter sein als der "
                   "letzte Lauf).")
    res_map = {r.id: r for r in results}
    datei = config.DATA_DIR / "auswahl_begruendung.json"
    eintraege: list[dict] = []
    if datei.exists():
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
            eintraege = [e for e in (daten.get("eintraege") or [])
                         if e.get("status") != "DRAUSSEN"]
            if daten:
                st.caption(f"Auswahl-Stand: {daten.get('zeitstempel', '?')}"
                           + (f" · Modus {daten.get('modus')}" if daten.get("modus") else ""))
        except (OSError, ValueError):
            eintraege = []
    if not eintraege and not results:
        st.info("Noch keine Kandidaten und kein Lauf-Ergebnis. Nach einem Scan "
                "steht hier für jedes Signal, ob es geprüft wurde — und das "
                "Ergebnis.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    zeilen = []
    for e in eintraege:
        status = str(e.get("status") or "KANDIDAT")
        r = res_map.get(e.get("id"))
        if r is not None:
            r.refresh_efficiency()
        geprueft = r is not None and r.forensik_vorhanden
        zeilen.append({
            "Geprüft": "✓ ja" if geprueft else "— nein",
            "Signal": e.get("name") or f"#{e.get('id')}",
            "ID": e.get("id"),
            "Quelle": e.get("quelle") or "mql5",
            "Ampel": (r.ampel if r else None),
            "Score": (r.score if geprueft else None),
            "Max-Drawdown % (Equity)": (r.max_drawdown_equity_pct if geprueft else None),
            "Trading-DD % (geschlossen)": (r.trading_dd_pct if geprueft else None),
            "Equity-Messung": (r.equity_messung_status if r else "Noch nicht geprüft"),
            "Gewinn %/Monat": (getattr(r, "ertrag_monat_geom_pct", None)
                         if geprueft else None),
            "RetDD": (getattr(r, "retdd_monat", None) if geprueft else None),
            "Grund": (e.get("grund") or "")
                     + ((" · ⚠ " + (r.fehler or "")[:90]) if r and r.fehler else ""),
            "Link": _signal_link(e),
            "_gewaehlt": geprueft,
        })
    # Ergebnisse ohne Eintrag in der Begründungsliste (z. B. ältere DB-Zeilen
    # ohne Lauf in der Datei) dürfen nicht still verschwinden.
    bekannte = {z["ID"] for z in zeilen}
    for r in results:
        if r.id in bekannte or not r.forensik_vorhanden:
            continue
        r.refresh_efficiency()
        zeilen.append({
            "Geprüft": "✓ ja", "Signal": r.name, "ID": r.id,
            "Quelle": r.quelle or "mql5", "Ampel": r.ampel, "Score": r.score,
            "Max-Drawdown % (Equity)": r.max_drawdown_equity_pct,
            "Trading-DD % (geschlossen)": r.trading_dd_pct,
            "Equity-Messung": r.equity_messung_status,
            "Gewinn %/Monat": getattr(r, "ertrag_monat_geom_pct", None),
            "RetDD": getattr(r, "retdd_monat", None),
            "Grund": "Aus dem Datenbank-Stand (kein Eintrag in der gespeicherten "
                     "Auswahl dieses Laufs).",
            "Link": _signal_link({"url": r.url, "id": r.id,
                                  "quelle": r.quelle or "mql5"}),
            "_gewaehlt": True})
    if eintraege:
        n_da = sum(1 for z in zeilen if z["_gewaehlt"])
        st.caption(f"**{len(zeilen)} Kandidaten im Lauf — {n_da} geprüft, "
                   f"{len(zeilen) - n_da} nicht geprüft** (Grund je Signal "
                   "in der Tabelle).")
    n_gesamt = len(zeilen)
    zeilen = _filterleiste(zeilen, "forensik",
                           label_gewaehlt="Nur geprüft",
                           label_raus="Nur nicht geprüft")
    st.caption(f"Angezeigt: {len(zeilen)} von {n_gesamt} Kandidaten.")
    st.dataframe(_ohne_intern(zeilen), width="stretch", hide_index=True,
                 column_config={"Link": _link_spalte()})
    st.caption("Max-Drawdown (Equity) enthält offene Gewinne und Verluste "
               "aus belastbaren Kurs- oder Monitor-Messungen; ohne diese "
               "bleibt das Feld leer. Trading-DD berücksichtigt nur "
               "geschlossene Trades. Die Schranke verwendet zusätzlich "
               "die Plattform-Angaben. Gewinn %/Monat ist die eigene geometrische "
               "Monatsrendite; RetDD teilt sie durch den gemessenen maximalen "
               "Equity-Drawdown. Geschlossener Drawdown dient nicht als Nenner.")
    probleme = [r for r in results if r.fehler]
    if probleme:
        st.warning(f"{len(probleme)} Signal(e) mit Fehler — Details auf der "
                   "Ergebnisseite unter „Probleme in diesem Lauf“.")


@st.dialog("🧠 Station 4 · KI-Berichte", width="large")
def _dialog_llm() -> None:
    """KI-Berichte: welche Signale bekamen Berichte und wie ausführlich."""
    import pandas as pd
    st.markdown("**Was passiert hier?** Die optionalen KI-Schritte beschreiben "
                "Strategie und Risiko anhand der Trades und berechneten Befunde "
                "und erstellen einen Gesamtbericht. Die Tabelle zeigt, welche "
                "Berichte für jedes Signal vorliegen.")
    results = list(st.session_state.get("scan_results") or [])
    if not results:
        try:
            results = list(pipeline.results_from_db(settings))
            if results:
                st.caption("Kein Lauf in dieser Sitzung — angezeigt ist der "
                           "letzte gespeicherte Datenbank-Stand.")
        except Exception:
            results = []
    if not results:
        st.info("Noch kein Lauf-Ergebnis in dieser Sitzung. Berichte erscheinen "
                "nach Station 4, sofern KI-Berichte eingeschaltet sind.")
        st.dataframe([], width="stretch", hide_index=True)
        return
    data = [{"Signal": r.name, "Quelle": r.quelle or "mql5", "Ampel": r.ampel,
             "Trade-Analyse": "✓" if getattr(r, "trade_analyse", "") else "—",
             "Risiko-Analyse": "✓" if getattr(r, "risiko_analyse", "") else "—",
             "Gesamtbericht": "✓" if getattr(r, "gesamtbericht", "") else "—",
             "Kurzfassung": (getattr(r, "kurzfassung", "") or "")[:120],
             "Link": _signal_link({"url": r.url, "id": r.id,
                                   "quelle": r.quelle or "mql5"}),
             "_gewaehlt": bool(getattr(r, "gesamtbericht", ""))}
            for r in results]
    data = _filterleiste(data, "llm", label_gewaehlt="Nur mit Bericht",
                         label_raus="Nur ohne Bericht")
    st.dataframe(_ohne_intern(data), width="stretch", hide_index=True,
                 column_config={"Link": _link_spalte()})
    st.caption("Nur 🟢/🟡 erhalten das volle KI-Paket (Design-Regel: Budget sparen).")


@st.dialog("🥧 Station 5 · Portfolio", width="large")
def _dialog_portfolio() -> None:
    """Portfolio-Vorschlag: Empfehlung und Statistik-Deutung."""
    st.markdown("**Was passiert hier?** Die KI führt die Berichte der 🟢/🟡-Signale "
                "zusammen. Code-Befunde zu gemeinsamen Verlustmonaten, "
                "Historienlänge und Instrument-Überschneidungen helfen, "
                "Kombinationen und Klumpenrisiken einzuschätzen. Historische "
                "Diversifikation ist keine Prognose.")
    st.dataframe([
        {"Prüfung": "Gemeinsame Verluste", "Grundlage": "Monate mit mehreren gleichzeitig verlierenden Signalen"},
        {"Prüfung": "Beobachtungsfenster", "Grundlage": "Historienlänge je Signal und gemeinsamer Zeitraum"},
        {"Prüfung": "Klumpenrisiko", "Grundlage": "Gemeinsame Instrumente und Rendite-Risiko-Effizienz"},
    ], width="stretch", hide_index=True)
    p = st.session_state.get("portfolio_result") or {}
    text = p.get("text") or st.session_state.get("portfolio_bericht") or ""
    if not text:
        st.info("Noch kein Portfolio in diesem Lauf — läuft nach dem letzten KI-Bericht.")
        return
    st.markdown(text[:8000])
    if len(text) > 8000:
        st.caption("… (gekürzt — vollständiger Bericht auf der Ergebnisseite)")
    # Welche Signale in die Portfolio-Bewertung eingeflossen sind (Nutzer-
    # Wunsch 02.10.: Herkunft je Signal sichtbar + Link zum Ursprung).
    basis = [r for r in (st.session_state.get("scan_results") or [])
             if r.ampel in ("🟢", "🟡")]
    if not basis:
        try:
            basis = [r for r in pipeline.results_from_db(settings)
                     if r.ampel in ("🟢", "🟡")]
        except Exception:
            basis = []
    if basis:
        for r in basis:
            r.refresh_efficiency()
        st.caption("Eingeflossen sind die 🟢/🟡-Signale des Laufs (Datenbasis "
                   "der KI-Zusammenfassung):")
        st.dataframe([{"Signal": r.name, "Quelle": r.quelle or "mql5",
                       "Ampel": r.ampel, "Ertrag/M (geom.)":
                       getattr(r, "ertrag_monat_geom_pct", None),
                       "RetDD": getattr(r, "retdd_monat", None),
                       "Link": _signal_link({"url": r.url, "id": r.id,
                                             "quelle": r.quelle or "mql5"})}
                      for r in basis], width="stretch", hide_index=True,
                     column_config={"Link": _link_spalte()})


@st.dialog("🔄 Station 6 · Abgleich", width="large")
def _dialog_downloader() -> None:
    """Downloader-Abgleich: was gespiegelt wurde."""
    import pandas as pd
    st.markdown("**Was passiert hier?** Der Abgleich lädt Abonnenten-Verläufe "
                "und vorhandene Testreport-PDFs aus den aktiven Datenquellen. "
                "Bereits vorhandene Dateien werden anhand ihres Inhalts erkannt. "
                "Ein Teilausfall wird protokolliert; die Bewertung der Signale "
                "ändert sich durch diesen Schritt nicht.")
    step = (st.session_state.get("scan_workflow") or {}).get("steps", {}).get("downloader") or {}
    st.dataframe([
        {"Eintrag": "Status", "Wert": STATES.get(step.get("status"), ("Noch nicht gestartet",))[0]},
        {"Eintrag": "Fortschritt", "Wert": f"{step.get('done', 0)} von {step.get('total') or '—'} Signalen"},
        {"Eintrag": "Befund", "Wert": step.get("detail") or "Noch nicht gestartet"},
    ], width="stretch", hide_index=True)
    log = list((st.session_state.get("scan_logs") or {}).get("downloader") or [])
    if log:
        st.dataframe(pd.DataFrame({"Abgleich-Protokoll": log}), width="stretch", hide_index=True)
    else:
        st.info("Noch kein Abgleich-Protokoll in dieser Sitzung. Nach Station 6 "
                "erscheinen hier die geladenen Daten und Hinweise.")
    st.caption("Die gespeicherten Abonnenten-Verläufe und PDFs sind auf der Ergebnisseite erreichbar.")


_station_dialoge = {
    "listen": _dialog_listen, "kandidaten": _dialog_auswahl,
    "forensik": _dialog_forensik, "llm": _dialog_llm,
    "portfolio": _dialog_portfolio, "downloader": _dialog_downloader,
}


@st.fragment(key="scan_station_dialog_host")
def _station_dialog_host() -> None:
    """Dialog-Lebensdauer unabhängig vom sekündlichen Status-Fragment.

    Der Stations-Callback rerunnt nur diesen Host; st.dialog übernimmt
    anschließend die Reruns seiner Filter. Der Trigger wird einmal verbraucht.
    """
    station = st.session_state.pop("_scan_station_dialog", None)
    if station is None:
        station = (st.query_params.get("station") or "").strip()
    if "station" in st.query_params:
        del st.query_params["station"]
    if station in _station_dialoge:
        _station_dialoge[station]()


# Nach den Dialogdefinitionen in jedem App-Lauf registrieren; dadurch ist der
# Host als Ziel für Stationsklicks verfügbar. Alte Stations-URLs bleiben gültig.
_station_dialog_host()


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
    render_downloader_docs_panel(results)
    selected = render_results_table(results, fix_ids=fix_signale.fix_ids())
    if selected is not None:
        from mqlkiscanner.app_ui import render_detail
        render_detail(selected)
else:
    with st.container(border=True, key="scan_empty"):
        st.markdown(":material/insights: **Noch keine Ergebnisse.**")
        st.caption(
            "Drücken Sie oben „Full-Scan“ oder „Teilscan“. "
            "Oder unter „Weitere Möglichkeiten“ nur die Testdaten prüfen.")
lauf_wechsel = (st.session_state.get("scan_control") or {}).get("ampel_wechsel") or []
if lauf_wechsel:
    section_header(
        "⚡ Ampel-Wechsel in diesem Lauf",
        "Jeder Wechsel ist dauerhaft protokolliert (Datenbank) — mit Begründung je Kriterium. "
        "Das vollständige Protokoll aller Läufe steht auf der Ergebnisseite.",
        help_key="wechsel_protokoll",
    )
    render_wechsel_karten(lauf_wechsel)
if st.session_state.get("portfolio_bericht"):
    with st.container(border=True, key="portfolio_panel"):
        st.subheader(":material/pie_chart: Portfolio-Vorschlag (Station 5)")
        st.caption("KI-Empfehlung über alle geprüften Signale: Strategie-Mix, Assets, "
                   "Gewichtung. Keine Anlageberatung.")
        portfolio_result = st.session_state.get("portfolio_result") or {
            "text": st.session_state.portfolio_bericht,
        }
        # Detail-Anhang je empfohlener Strategie (Nutzer-Wunsch 30.09.2026):
        # die 🟢-Ergebnisse des Laufs liefern die vollständigen Berichte.
        render_portfolio_pdf_viewer(
            portfolio_result, key="scan_portfolio_pdf",
            ergebnisse=[r for r in (st.session_state.get("results") or [])
                        if getattr(r, "ampel", "") == "🟢"
                        and getattr(r, "gesamtbericht", "")])
        st.markdown(urteile_farbig(st.session_state.portfolio_bericht),
                    unsafe_allow_html=True)
        if issue := portfolio_result.get("storage_error") or portfolio_result.get("reason"):
            st.warning(f"Portfolio-Hinweis: {issue}")


def _begruendung_speichern(begruendung: list[dict], top_n: int,
                           modus: str = "") -> None:
    """Auswahl-Begründung je Signal ablegen (Station-Dialog „Auswahl treffen")."""
    try:
        datei = config.DATA_DIR / "auswahl_begruendung.json"
        datei.write_text(json.dumps({
            "zeitstempel": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "top_n_export": top_n,
            "modus": modus,
            "eintraege": begruendung,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
