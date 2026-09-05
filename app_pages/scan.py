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

import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, db, pipeline, secrets_store
from mqlkiscanner.app_ui import render_report_panel, render_results_table
from mqlkiscanner.ui_design import (
    action_button, apply_theme, page_header, section_header, urteile_farbig,
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
        "finished_at": None, "activity": "Bereit. Drücken Sie „Starte Workflow“.", "saved": False,
        "steps": {sid: {"status": "pending", "done": 0, "total": None,
                        "detail": "Noch nicht gestartet", "unit": unit}
                  for sid, _, _, unit, _ in STEPS},
    }


st.session_state.setdefault("scan_results", [])
st.session_state.setdefault("scan_logs", {})
st.session_state.setdefault("last_run_file", None)
st.session_state.setdefault("scan_workflow", _new_workflow())
st.session_state.setdefault("portfolio_bericht", "")
st.session_state.setdefault("scan_new_ids", [])
st.session_state.setdefault("scan_thread", None)
st.session_state.setdefault("scan_control", {})


def _lauf_ergebnisse_uebernehmen() -> None:
    """Beendetes Lauf-Thread: frische Ergebnisse in die Sitzung übernehmen.

    Wird beim vollen Seitenaufruf gerufen (der Fragment-Tick stößt ihn an,
    sobald der Thread beendet ist) — so landen Portfolio-Bericht, letzte
    Laufdatei und Zwischenergebnisse sicher in der Session.
    """
    ctl = st.session_state.scan_control
    th = st.session_state.scan_thread
    if th is None or th.is_alive() or ctl.get("copied"):
        return
    st.session_state.portfolio_bericht = ctl.get("portfolio_bericht", "")
    st.session_state.scan_new_ids = ctl.get("new_ids", [])
    if ctl.get("signals") is not None:
        st.session_state["scan_signals"] = ctl["signals"]
    if ctl.get("candidates") is not None:
        st.session_state["scan_candidates"] = ctl["candidates"]
    if ctl.get("last_run_file"):
        st.session_state.last_run_file = ctl["last_run_file"]
    if ctl.get("refreshed_ids") is not None:
        st.session_state.refreshed_signal_ids = ctl["refreshed_ids"]
    ctl["copied"] = True
    st.session_state.scan_running = None
    wf = st.session_state.scan_workflow
    if wf["status"] == "running":
        # Hart gestorbener Worker (App-Neustart mitten im Lauf): sauber beenden.
        wf.update(status="error",
                  activity="Lauf wurde unterbrochen. Vorliegende Ergebnisse bleiben erhalten.")
        for _step_state in wf["steps"].values():
            if _step_state["status"] == "running":
                _step_state.update(status="error", detail="Lauf unterbrochen; nicht abgeschlossen")
            elif _step_state["status"] == "pending":
                _step_state.update(status="skipped", detail="Nach Unterbrechung nicht ausgeführt")


def _stop_requested() -> None:
    """Button-Callback: Stop-Flag für den Worker setzen."""
    ctl = st.session_state.get("scan_control") or {}
    ctl["stop"] = True
    wf = st.session_state.get("scan_workflow")
    if wf:
        wf["activity"] = "Stop angefordert — der Lauf endet nach dem aktuellen Signal bzw. Modellaufruf."


command = st.session_state.pop("scan_command", None)
workflow = st.session_state.scan_workflow
control = st.session_state.scan_control
_lauf_thread = st.session_state.scan_thread
_thread_lebt = bool(_lauf_thread is not None and _lauf_thread.is_alive())

if command is None:
    _lauf_ergebnisse_uebernehmen()

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
    if command["mode"] == "scan" and command["settings"] and not (
            command["settings"]["llm_stufe1"] or command["settings"]["llm_stufe2"]):
        workflow["steps"]["llm"].update(status="skipped", detail="KI-Berichte für diesen Lauf ausgeschaltet")
        workflow["steps"]["portfolio"].update(status="skipped", detail="Portfolio-Vorschlag für diesen Lauf ausgeschaltet")
    if command["mode"] in ("scan", "step_listen"):
        st.session_state.scan_results = []
        st.session_state.scan_logs = {}
        st.session_state.last_run_file = None
        st.session_state.portfolio_bericht = ""
    if command["mode"] in ("scan", "local"):
        st.session_state.scan_new_ids = []

settings = config.load_settings()
running = command is not None or _thread_lebt
hero_banner = Path(__file__).resolve().parents[1] / "assets" / "hero_scan_banner.jpg"
page_header(
    "WORKFLOW",
    "So prüft der Scanner Signale",
    "Ein fester Ablauf: Daten holen → speichern → rechnerisch prüfen → "
    "optional KI-Berichte und Portfolio-Vorschlag. Ein Knopf startet alles.",
    image_path=str(hero_banner) if hero_banner.exists() else None,
)
section_header(
    "Der Workflow",
    "Fünf klare Stationen. Sie müssen nichts einzeln anstoßen — "
    "„Starte Workflow“ macht den kompletten Durchlauf.",
    help_key="scan_workflow",
)


@st.fragment(run_every=1.0)
def _workflow_status() -> None:
    """Live-Statusbereich (Fragment): alle 1 s NUR diesen Bereich neu zeichnen."""
    workflow = st.session_state.scan_workflow
    control = st.session_state.scan_control
    # Snapshot: Der Worker-Thread darf while wir rendern in das Dict schreiben.
    steps_state = {sid: dict(step) for sid, step in workflow["steps"].items()}
    first_pending = next(
        (sid for sid, *_ in STEPS if steps_state[sid]["status"] == "pending"),
        None,
    )
    laufende = [sid for sid, *_ in STEPS if steps_state[sid]["status"] == "running"]

    # Glow-CSS für laufende Karten — eigener Markdown-Block, damit der
    # Kartenkopf-Markdown (Icon-Makro, Fettmarkierung) sauber bleibt.
    if laufende:
        regeln = []
        for sid in laufende:
            regeln.append(
                f".st-key-workflow_{sid}{{border-color:#79D8DAB0!important;"
                f"box-shadow:0 0 0 1px rgba(121,216,218,.4),"
                f"0 0 .8rem rgba(121,216,218,.3)!important;"
                f"animation:mks-card-glow 1.5s ease-in-out infinite;}}"
                f'.st-key-workflow_{sid} [data-testid="stBadge"]'
                f"{{animation:mks-badge-glow 1.5s ease-in-out infinite;}}"
                f'.st-key-workflow_{sid} [data-testid="stBadge"] svg,'
                f'.st-key-workflow_{sid} [data-testid="stIconMaterial"]'
                f"{{animation:mks-spin 1.1s linear infinite;display:inline-block;"
                f"transform-origin:center;}}")
        st.markdown("<style>" + "".join(regeln) + "</style>", unsafe_allow_html=True)

    # Stationskarten mit Pfeil-Verbindern dazwischen (eine Reihe).
    layout = st.columns([*([1, 0.14] * (len(STEPS) - 1)), 1], gap="small")
    for col in layout[1::2]:
        col.markdown('<div class="mks-connector" aria-hidden="true">→</div>',
                     unsafe_allow_html=True)
    for nr, (col, (sid, title, icon, _unit, beschreibung)) in enumerate(
            zip(layout[0::2], STEPS), 1):
        step = steps_state[sid]
        # Nur der nächste offene Schritt blinkt — Hinweis „hier geht es weiter“.
        blink = (
            sid == first_pending
            and workflow["status"] != "running"
            and step["status"] == "pending"
        )
        run_cls = " mks-runnum" if step["status"] == "running" else ""
        with col.container(border=True, key=f"workflow_{sid}", height="stretch"):
            st.markdown(
                f'<span class="mks-stepnum{" mks-blink" if blink else ""}{run_cls}">{nr}</span>'
                f':material/{icon}: **{title}**'
                f'<br><span class="mks-flow-text">{beschreibung}</span>',
                unsafe_allow_html=True)
            label, color, state_icon = STATES[step["status"]]
            st.badge(label, color=color, icon=f":material/{state_icon}:")
            st.caption(step["detail"])
            if step["total"] and step["status"] != "skipped":
                st.progress(min(step["done"] / step["total"], 1.0),
                            text=f"{step['done']}/{step['total']} {step['unit']}")

    active = next((title for sid, title, *_ in STEPS
                   if steps_state[sid]["status"] == "running"), None)
    pending = [title for sid, title, *_ in STEPS
               if steps_state[sid]["status"] == "pending"]
    next_text = " → ".join(pending) if pending else (
        "Ergebnisse speichern" if workflow["status"] == "running"
        else "Ergebnisse ansehen oder Workflow erneut starten")
    finished = sum(s["status"] == "complete" for s in steps_state.values())
    warnings = sum(s["status"] == "warning" for s in steps_state.values())
    skipped = sum(s["status"] == "skipped" for s in steps_state.values())
    errors = sum(s["status"] == "error" for s in steps_state.values())
    with st.container(border=True, key="scan_activity", gap="xsmall"):
        st.markdown(f"**{'Aktuell: ' + active if active else 'Status'}** · {workflow['activity']}")
        st.caption(f"Als Nächstes: {next_text}")
        st.caption(
            f"{finished}/{len(STEPS)} Stationen fertig · {warnings} mit Hinweisen · "
            f"{skipped} übersprungen · {errors} fehlgeschlagen. "
            "Die Balken zählen erledigte Arbeit, keine Uhrzeit.")

    # Lauf beendet? Einmal die GANZE Seite neu laden: Ergebnisübernahme
    # (Session) + Endstand (Tabelle, Portfolio, Protokoll) rendern.
    th = st.session_state.scan_thread
    if th is not None and not th.is_alive() and not control.get("copied"):
        st.rerun(scope="app")


_workflow_status()

section_header(
    "Workflow starten",
    "Ein Klick reicht für den kompletten Durchlauf. Einstellungen und "
    "Sonderfälle finden Sie darunter.",
)
has_login = bool(secrets_store.get_secret("mql5_user") and secrets_store.get_secret("mql5_pass"))
has_llm = bool(secrets_store.get_secret("glm_api_key"))
with st.container(border=True, key="scan_start_panel"):
    st.markdown("**Was passiert nach dem Start?**")
    st.caption(
        "1) Signale von MQL5 holen · 2) ungeeignete aussortieren · "
        "3) Handelsdaten laden, speichern und rechnerisch prüfen · "
        "4) optional KI-Berichte schreiben · 5) Portfolio-Vorschlag über alle Signale."
    )
    start_zeile = st.columns([1, 1], gap="small", vertical_alignment="center")
    with start_zeile[0]:
        start = action_button(
            "Starte Workflow",
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
    nur_neue = st.toggle(
        "Nur neue Signale bewerten — alte Bewertungen übernehmen",
        key="scan_nur_neue",
        disabled=running,
    )
    st.caption(
        "An: Bereits gründlich bewertete Signale werden nicht erneut von MQL5 "
        "geladen — ihre Bewertungen bleiben unverändert und erscheinen trotzdem "
        "im Ergebnis. Der Portfolio-Vorschlag (Station 5) nutzt immer alle Signale."
    )
    with st.container(horizontal=True, gap="small"):
        st.badge("MQL5-Zugang ok" if has_login else "MQL5-Zugang fehlt",
                 icon=":material/lock:", color="blue" if has_login else "orange")
        st.badge("KI-Key ok" if has_llm else "KI optional · Key fehlt",
                 icon=":material/key:", color="blue" if has_llm else "gray")
    if not has_login:
        st.caption(
            "Ohne MQL5-Zugang unter Einstellungen können Listen geladen werden, "
            "aber keine vollständigen Handelsdaten. Dann bleibt es bei einer Vorprüfung.")

with st.expander("Einstellungen für diesen Lauf", icon=":material/tune:", expanded=False):
    left, right = st.columns(2)
    with left.container(border=True, key="scan_scope"):
        section_header("Wie weit suchen?", "Weniger Seiten = schnellerer Lauf.", help_key="scan_scope")
        pages = st.number_input(
            "Listen-Seiten je MT4/MT5", 1, 10, value=int(settings["listen_seiten"]),
            key="set_seiten", disabled=running)
        top_n = st.number_input(
            "Max. Signale gründlich prüfen", 1, 50, value=int(settings["top_n_export"]),
            key="set_topn", disabled=running)
    with right.container(border=True, key="scan_filters"):
        section_header("Vorfilter", "Nur Signale, die alt genug und sichtbar genug sind.",
                       help_key="scan_filters")
        min_weeks = st.number_input(
            "Mindestalter in Wochen", 0, 260, value=int(settings["min_wochen"]),
            key="set_wochen", disabled=running)
        min_subs = st.number_input(
            "Mindestens Abonnenten", 0, 1000, value=int(settings["min_abonnenten"]),
            key="set_abo", disabled=running)
    with st.container(border=True, key="scan_llm_settings"):
        section_header("KI am Ende?", "Nach dem Rechnen drei Berichte je Signal, danach der Portfolio-Vorschlag.",
                       help_key="scan_llm_settings")
        use_llm = st.toggle(
            "KI-Berichte nach dem Workflow erstellen",
            key="scan_use_llm",
            value=bool(settings["llm_stufe1"] or settings["llm_stufe2"]),
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
            "Aus (Standard): Signale mit bereits gespeichertem Gesamtbericht werden "
            "übersprungen — ihr Bericht wird aus der Datenbank geladen. "
            "An: alle Berichte werden neu erzeugt (Dauer + Tokens)." if not berichte_neu else
            "An: ALLE Berichte werden neu erzeugt — vorhandene werden ersetzt "
            "(in der Datenbank bleibt die Historie erhalten)."
        )
    st.caption("Sichtbare Werte gelten sofort. Speichern macht sie zum Standard für später.")
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

with st.expander("Weitere Möglichkeiten", icon=":material/more_horiz:", expanded=False):
    st.caption("Nur nötig, wenn Sie nicht den kompletten Online-Workflow wollen.")
    vcol, lcol = st.columns(2, gap="small")
    with vcol.container(border=True, key="scan_source_local", height="stretch"):
        st.markdown(":material/fact_check: **Nur Testdaten prüfen**")
        st.caption("Vorhandene Dateien in data/raw analysieren — ohne Internet und ohne neue KI.")
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
            disabled=running or not st.session_state.scan_results,
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
    control = {"stop": False, "portfolio_bericht": "", "new_ids": [],
               "signals": None, "candidates": None,
               "last_run_file": None, "refreshed_ids": None, "copied": False}
    st.session_state.scan_control = control
    st.session_state.scan_running = mode if mode != "scan" else "listen"
    pipe = pipeline.ScanPipeline(run_config)

    def w_step(sid: str, status: str | None = None, **values) -> None:
        if status:
            values["status"] = status
        workflow["steps"][sid].update(values)
        if "detail" in values:
            workflow["activity"] = values["detail"]

    def w_log_for(sid: str):
        lines = logs.setdefault(sid, [])

        def log(message: str) -> None:
            lines.append(message)
            workflow["activity"] = message.splitlines()[0][:400]
        return log

    def w_run_listen(cfg) -> list[dict]:
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
        w_step("kandidaten", "running", total=len(signals),
               detail="Alter und Abonnenten prüfen …")
        candidates = pipe.build_candidates(signals, w_log_for("kandidaten"))
        control["candidates"] = candidates
        w_step("kandidaten", "complete", done=len(signals),
               detail=f"{len(candidates)} passende Signale aus {len(signals)}")
        return candidates

    def w_run_forensik(cands: list[dict], cfg) -> None:
        n_export = min(len(cands), cfg["top_n_export"])
        if not n_export:
            w_step("forensik", "skipped", detail="Keine passenden Signale nach der Auswahl")
            return
        only_new = bool(cfg.get("nur_neue"))
        alt: dict[int, pipeline.ScanResult] = {}
        if only_new:
            alt = {r.id: r for r in pipeline.results_from_db(cfg) if r.forensik_vorhanden}
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
                result = pipe.analyze_candidate(session, candidate, log)
                results.append(result)
                new_ids.append(result.id)
            except pipeline.Mql5HardStopError as exc:
                if getattr(exc, "result", None) is not None:
                    results.append(exc.result)
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
        good = sum(r.forensik_vorhanden and not r.fehler for r in results)
        errors = sum(bool(r.fehler) for r in results)
        preview = len(results) - good - errors
        zusatz = f" · {len(uebernommen)} übernommen" if uebernommen else ""
        if stopped_early:
            w_step("forensik", "warning", done=n_export,
                   detail=(f"Abbruch zum Account-Schutz · {good} geprüft · "
                           f"{preview} Vorprüfung · {errors} Fehler{zusatz}"))
        elif stop_gefordert:
            w_step("forensik", "warning", done=n_export,
                   detail=(f"Abbruch per Stop-Button · {good} geprüft · "
                           f"{preview} Vorprüfung · {errors} Fehler{zusatz}"))
        else:
            w_step(
                "forensik", done=n_export,
                status="complete" if good == len(results) else "error" if errors == len(results) else "warning",
                detail=(f"{good} gründlich geprüft · {preview} nur Vorprüfung · "
                        f"{errors} mit Fehlern{zusatz}"),
            )

    def w_run_llm(targets: list[pipeline.ScanResult], cfg) -> None:
        kandidaten = [r for r in targets if r.forensik_vorhanden and not r.fehler]
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
                vorhanden = db.get_latest_analysis(r.id, "gesamtbericht")
                if vorhanden is None:
                    jobs.append(r)
                    continue
                uebersprungen.append(r)
                r.gesamtbericht = vorhanden["text"]
                if not r.kurzfassung:
                    r.kurzfassung = pipeline._extract_kurzfassung(vorhanden["text"])
                for kind, attr in (("trade_analyse", "trade_analyse"),
                                   ("risiko_analyse", "risiko_analyse")):
                    prev = db.get_latest_analysis(r.id, kind)
                    if prev:
                        setattr(r, attr, prev["text"])
        total = 3 * len(jobs)
        if uebersprungen:
            namen = ", ".join(f"#{r.id} {r.name}" for r in uebersprungen[:8])
            if len(uebersprungen) > 8:
                namen += f" … (+{len(uebersprungen) - 8})"
            logs.setdefault("llm", []).append(
                f"{len(uebersprungen)} Signale mit vorhandenem Bericht übersprungen "
                f"(aus der Datenbank geladen): {namen}")
        if not pipe.llm.has_key or not total:
            if not jobs and uebersprungen:
                w_step("llm", "complete", done=0, total=0,
                       detail=(f"Alle {len(uebersprungen)} Signale haben bereits Berichte — "
                               "aus der Datenbank geladen, nichts neu erzeugt"))
                return
            reason = "Kein KI-Key hinterlegt" if not pipe.llm.has_key else "Keine geeigneten Prüfergebnisse"
            logs["llm"] = logs.get("llm", []) + [reason]
            w_step("llm", "skipped", detail=reason, total=total)
            return
        w_step("llm", "running", total=total, detail="Trade-Analyse wird vorbereitet")
        summary = pipe.run_llm(
            jobs, w_log_for("llm"),
            on_progress=lambda done, total, text: w_step("llm", done=done, total=total, detail=text),
            should_stop=lambda: bool(control.get("stop")),
        )
        completed, total = summary["completed"], summary["total"]
        failed, skipped = summary["failed"], summary["skipped"]
        if (summary.get("reason") or "").startswith("Abbruch"):
            state = "warning"
        else:
            state = "complete" if completed == total else "warning" if completed else "error"
        detail = (
            f"{completed}/{total} Berichte gespeichert · {failed} fehlgeschlagen · "
            f"{skipped} nicht ausgeführt · {pipe.llm.usage.total_tokens:,} Tokens"
        )
        if uebersprungen:
            detail += f" · {len(uebersprungen)} übersprungen (Bericht vorhanden)"
        if summary["reason"]:
            detail += f". {summary['reason']}"
        w_step("llm", state, done=completed, total=total, detail=detail)

    def w_run_portfolio(alle: list[pipeline.ScanResult], cfg) -> None:
        if not pipe.llm.has_key:
            logs["portfolio"] = ["Kein KI-Key hinterlegt"]
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
        if summary.get("text"):
            control["portfolio_bericht"] = summary["text"]
            w_step("portfolio", "complete", done=1,
                   detail=(f"Portfolio-Vorschlag erstellt · {summary.get('zeichen', 0):,} Zeichen · "
                           f"{summary.get('tokens', 0):,} Tokens gesamt"))
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
                        for i, file in enumerate(files):
                            w_step("forensik", detail=f"Datei {i + 1}/{len(files)}: {file.name}", done=i)
                            rows = pipeline.ScanPipeline.analyze_local_files([str(file)], run_config)
                            results.extend(rows)
                            log(f"{file.name}: " + ("Fehler" if any(r.fehler for r in rows) else "analysiert"))
                            w_step("forensik", done=i + 1)
                        good = sum(r.forensik_vorhanden and not r.fehler for r in results)
                        bad = len(results) - good
                        w_step(
                            "forensik",
                            "complete" if not bad else "warning" if good else "error",
                            detail=f"{good} Dateien geprüft · {bad} fehlerhaft",
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
                    ki_an = run_config["llm_stufe1"] or run_config["llm_stufe2"]
                    gestoppt = bool(control.get("stop"))
                    if ki_an and not gestoppt:
                        # Im Nur-neue-Modus nur die frisch geprüften Signale neu
                        # berichten; der Portfolio-Vorschlag sieht alle Signale.
                        current_step = "llm"
                        targets = results
                        frisch = set(control.get("new_ids") or [])
                        if run_config.get("nur_neue") and frisch:
                            targets = [r for r in results if r.id in frisch]
                        w_run_llm(targets, run_config)
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
                logs.setdefault(current_step, []).append(f"FEHLER: {message}")
                w_step(current_step, "error", detail=message)
                for sid, *_ in STEPS:
                    if workflow["steps"][sid]["status"] == "pending":
                        w_step(sid, "skipped", detail="Nach vorherigem Fehler nicht ausgeführt")
            workflow["activity"] = "Ergebnisse und Protokoll speichern …"
            try:
                control["last_run_file"] = pipeline.ScanPipeline.save_run(results, logs)
                control["refreshed_ids"] = [r.id for r in results]
                workflow["saved"] = True
            except Exception as exc:
                workflow.update(status="error", activity=f"Speichern fehlgeschlagen: {exc}")
            states = [s["status"] for s in workflow["steps"].values()]
            if workflow["saved"]:
                final_status = (
                    "error" if "error" in states
                    else "warning" if "warning" in states or all(s == "skipped" for s in states)
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

    _lauf_thread = threading.Thread(target=_worker, name="mqlkiscanner-workflow", daemon=True)
    st.session_state.scan_thread = _lauf_thread
    st.session_state.scan_running = mode if mode != "scan" else "listen"
    _lauf_thread.start()

section_header(
    "Ergebnisse dieses Laufs",
    "Fertig heißt: der Ablauf ist durch. Es ist noch keine Kaufempfehlung.",
    help_key="scan_results",
)
if st.session_state.scan_results:
    results = st.session_state.scan_results
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Datensätze", len(results), border=True)
    c2.metric("Gründlich geprüft", sum(r.forensik_vorhanden for r in results), border=True)
    c3.metric("Kandidaten", sum(r.ampel == "🟢" for r in results), border=True)
    c4.metric("Fehler / Vorprüfung",
              sum(bool(r.fehler) or not r.forensik_vorhanden for r in results), border=True)
    render_report_panel(results)
    selected_id = render_results_table(results)
    if selected_id is not None:
        from mqlkiscanner.app_ui import render_detail
        render_detail(next(r for r in results if r.id == selected_id))
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
        st.markdown(urteile_farbig(st.session_state.portfolio_bericht),
                    unsafe_allow_html=True)
if st.session_state.scan_logs:
    with st.expander("Ablaufprotokoll (technisch)", icon=":material/receipt_long:"):
        for sid, title, *_rest in STEPS:
            lines = st.session_state.scan_logs.get(sid, [])
            if lines:
                st.markdown(f"**{title}**")
                st.code("\n".join(lines), language=None, wrap_lines=True)
