# -*- coding: utf-8 -*-
"""Scan-Arbeitsplatz: ein Workflow von MQL5-Daten bis zum KI-Bericht."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, pipeline, secrets_store
from mqlkiscanner.app_ui import render_report_panel, render_results_table
from mqlkiscanner.ui_design import action_button, page_header, section_header

# Interne Status-Schritte (IDs stabil für Pipeline/Tests).
STEPS = (
    ("listen", "Signale holen", "cloud_download", "Seiten"),
    ("kandidaten", "Auswahl treffen", "filter_list", "Signale"),
    ("forensik", "Prüfen & speichern", "database", "Datensätze"),
    ("llm", "KI-Bericht", "psychology", "Berichte"),
)
# Laien-Erklärung des Ablaufs (was passiert — nicht 1:1 die Statuskarten).
WORKFLOW_STORY = (
    ("1", "Daten holen", "Signallisten und Handelsdaten von MQL5 laden"),
    ("2", "Speichern", "Alles in die lokale Datenbank legen"),
    ("3", "Computer prüft", "Webseite und CSV auf Risiko rechnen"),
    ("4", "KI berichtet", "Verständliche Texte und Endbericht schreiben"),
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
                  for sid, _, _, unit in STEPS},
    }


def _render_story() -> None:
    parts = []
    for i, (nr, title, text) in enumerate(WORKFLOW_STORY):
        if i:
            parts.append('<span class="mks-flow-arrow" aria-hidden="true">→</span>')
        parts.append(
            f'<div class="mks-flow-step">'
            f'<span class="mks-flow-num">{nr}</span>'
            f'<strong>{title}</strong>'
            f'<span class="mks-flow-text">{text}</span>'
            f"</div>"
        )
    st.markdown(
        '<div class="mks-flow" role="list">' + "".join(parts) + "</div>"
        '<p class="mks-flow-note">Ein Klick auf <strong>Starte Workflow</strong> führt diese Schritte '
        "nacheinander aus. Die Karten darunter zeigen den aktuellen Stand.</p>",
        unsafe_allow_html=True,
    )


st.session_state.setdefault("scan_results", [])
st.session_state.setdefault("scan_logs", {})
st.session_state.setdefault("last_run_file", None)
st.session_state.setdefault("scan_workflow", _new_workflow())
command = st.session_state.pop("scan_command", None)
workflow = st.session_state.scan_workflow
# Ein Widget-Rerun oder Seitenwechsel kann synchrone Arbeit unterbrechen.
# Beim nächsten Rendern einen solchen Lauf nicht weiter als „läuft“ anzeigen.
if command is None and workflow["status"] == "running":
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
    if command["mode"] in ("scan", "step_listen"):
        st.session_state.scan_results = []
        st.session_state.scan_logs = {}
        st.session_state.last_run_file = None

settings = config.load_settings()
running = command is not None
page_header(
    "WORKFLOW",
    "So prüft der Scanner Signale",
    "Ein fester Ablauf: Daten holen → speichern → rechnerisch prüfen → "
    "optional mit KI erklären. Ein Knopf startet alles.",
)
section_header(
    "Der Workflow",
    "Vier klare Stationen. Sie müssen nichts einzeln anstoßen — "
    "„Starte Workflow“ macht den kompletten Durchlauf.",
    help_key="scan_workflow",
)
_render_story()

heads = {}
cards = {}
for nr, (col, (sid, title, icon, _)) in enumerate(zip(st.columns(4, gap="small"), STEPS), 1):
    with col.container(border=True, key=f"workflow_{sid}", height="stretch"):
        heads[sid] = st.empty()
        cards[sid] = st.empty()
with st.container(border=True, key="scan_activity", gap="xsmall"):
    activity_slot = st.empty()
    next_slot = st.empty()
    counter_slot = st.empty()
with st.bottom:
    with st.container(key="workflow_footer", gap="xxsmall"):
        footer_slot = st.empty()


def _refresh_workflow() -> None:
    first_pending = next(
        (sid for sid, _, _, _ in STEPS if workflow["steps"][sid]["status"] == "pending"),
        None,
    )
    for nr, (sid, title, icon, _) in enumerate(STEPS, 1):
        step = workflow["steps"][sid]
        # Nur der nächste offene Schritt blinkt — Hinweis „hier geht es weiter“.
        blink = (
            sid == first_pending
            and workflow["status"] != "running"
            and step["status"] == "pending"
        )
        heads[sid].markdown(
            f'<span class="mks-stepnum{" mks-blink" if blink else ""}">{nr}</span>'
            f':material/{icon}: **{title}**', unsafe_allow_html=True)
        label, color, state_icon = STATES[step["status"]]
        with cards[sid].container(gap="xsmall"):
            st.badge(label, color=color, icon=f":material/{state_icon}:")
            st.caption(step["detail"])
            if step["total"] and step["status"] != "skipped":
                st.progress(min(step["done"] / step["total"], 1.0),
                            text=f"{step['done']}/{step['total']} {step['unit']}")
    active = next((title for sid, title, _, _ in STEPS
                   if workflow["steps"][sid]["status"] == "running"), None)
    pending = [title for sid, title, _, _ in STEPS
               if workflow["steps"][sid]["status"] == "pending"]
    next_text = " → ".join(pending) if pending else (
        "Ergebnisse speichern" if workflow["status"] == "running"
        else "Ergebnisse ansehen oder Workflow erneut starten")
    finished = sum(s["status"] == "complete" for s in workflow["steps"].values())
    warnings = sum(s["status"] == "warning" for s in workflow["steps"].values())
    skipped = sum(s["status"] == "skipped" for s in workflow["steps"].values())
    errors = sum(s["status"] == "error" for s in workflow["steps"].values())
    activity_slot.markdown(f"**{'Aktuell: ' + active if active else 'Status'}** · {workflow['activity']}")
    next_slot.caption(f"Als Nächstes: {next_text}")
    counter_slot.caption(
        f"{finished}/4 Stationen fertig · {warnings} mit Hinweisen · "
        f"{skipped} übersprungen · {errors} fehlgeschlagen. "
        "Die Balken zählen erledigte Arbeit, keine Uhrzeit.")
    with footer_slot.container(gap="xxsmall"):
        prefix = active or {
            "idle": "Bereit",
            "complete": "Workflow fertig",
            "warning": "Workflow mit Hinweisen beendet",
            "error": "Workflow mit Fehlern beendet",
        }.get(workflow["status"], "Ergebnisse werden gespeichert")
        st.markdown(
            f":material/{'autorenew' if workflow['status'] == 'running' else 'radar'}: "
            f"**{prefix}** · {workflow['activity']}")
        st.caption(
            f"Als Nächstes: {next_text}" if workflow["status"] == "running" else
            f"{finished}/4 Stationen fertig · {warnings} mit Hinweisen · "
            f"{skipped} übersprungen · {errors} fehlgeschlagen")


def _step(sid: str, status: str | None = None, **values) -> None:
    if status:
        values["status"] = status
    workflow["steps"][sid].update(values)
    if status == "running":
        st.session_state.scan_running = sid
    if "detail" in values:
        workflow["activity"] = values["detail"]
    _refresh_workflow()


_refresh_workflow()

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
        "4) optional KI-Berichte schreiben."
    )
    start = action_button(
        "Starte Workflow",
        key="scan_start",
        help_key="scan_start",
        type="primary",
        icon=":material/play_arrow:",
        disabled=running,
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
        section_header("KI am Ende?", "Nach dem Rechnen drei Berichte je geeignetem Signal.",
                       help_key="scan_llm_settings")
        use_llm = st.toggle(
            "KI-Berichte nach dem Workflow erstellen",
            key="scan_use_llm",
            value=bool(settings["llm_stufe1"] or settings["llm_stufe2"]),
            disabled=running,
        )
        st.caption("Trade- und Risiko-Analyse parallel, danach der Endbericht.")
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
        st.caption("Bereits geprüfte Ergebnisse dieser Sitzung mit KI erklären.")
        llm_only = action_button(
            "KI-Berichte starten",
            key="scan_llm",
            help_key="scan_llm",
            icon=":material/psychology:",
            disabled=running or not st.session_state.scan_results,
        )
    st.markdown("**Einzelschritte (Experten)**")
    st.caption("Normalerweise unnötig. Der Workflow-Button führt alle Stationen automatisch aus.")
    step_cols = st.columns(4, gap="small")
    for nr, (col, (sid, title, _, _)) in enumerate(zip(step_cols, STEPS), 1):
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
}
if save_settings:
    config.save_settings(run_settings)
    st.toast("Einstellungen gespeichert.", icon=":material/check:")
if start or verify or llm_only:
    st.session_state.scan_command = {
        "mode": "scan" if start else "local" if verify else "llm",
        "settings": run_settings,
    }
    st.rerun()


def _log_for(sid: str):
    lines = st.session_state.scan_logs.setdefault(sid, [])

    def log(message: str) -> None:
        lines.append(message)
        # Nur die Aktivitätszeile stammt aus dem Log. Status und Fortschritt
        # werden ausschließlich vom aufrufenden Ablauf bzw. Callback gesetzt.
        workflow["activity"] = message.splitlines()[0][:400]
        _refresh_workflow()
    return log


def _run_llm(results: list[pipeline.ScanResult], run_config: dict) -> None:
    pipe = pipeline.ScanPipeline(run_config)
    total = 3 * sum(r.forensik_vorhanden and not r.fehler for r in results)
    if not pipe.llm.has_key or not total:
        reason = "Kein KI-Key hinterlegt" if not pipe.llm.has_key else "Keine geeigneten Prüfergebnisse"
        st.session_state.scan_logs["llm"] = [reason]
        _step("llm", "skipped", detail=reason, total=total)
        return
    _step("llm", "running", total=total, detail="Trade-Analyse wird vorbereitet")
    summary = pipe.run_llm(
        results, _log_for("llm"),
        on_progress=lambda done, total, text: _step("llm", done=done, total=total, detail=text),
    )
    completed, total = summary["completed"], summary["total"]
    failed, skipped = summary["failed"], summary["skipped"]
    state = "complete" if completed == total else "warning" if completed else "error"
    detail = (
        f"{completed}/{total} Berichte gespeichert · {failed} fehlgeschlagen · "
        f"{skipped} nicht ausgeführt · {pipe.llm.usage.total_tokens:,} Tokens"
    )
    if summary["reason"]:
        detail += f". {summary['reason']}"
    _step("llm", state, done=completed, total=total, detail=detail)


if command:
    run_config = command["settings"] or run_settings
    mode = command["mode"]
    current_step = {
        "llm": "llm", "local": "forensik", "step_listen": "listen",
        "step_kandidaten": "kandidaten", "step_forensik": "forensik",
        "step_llm": "llm",
    }.get(mode, "listen")
    pipe = pipeline.ScanPipeline(run_config)

    def _run_listen(cfg) -> list[dict]:
        _step("listen", "running", total=2 * cfg["listen_seiten"],
              detail="MQL5-Listen abrufen …")
        signals = pipe.crawl(
            on_progress=lambda done, total, text: _step("listen", done=done, total=total, detail=text),
            log=_log_for("listen"),
        )
        st.session_state["scan_signals"] = signals
        _step("listen", "complete", detail=f"{len(signals)} Signale geladen")
        return signals

    def _run_kandidaten(signals: list[dict], cfg) -> list[dict]:
        _step("kandidaten", "running", total=len(signals),
              detail="Alter und Abonnenten prüfen …")
        candidates = pipe.build_candidates(signals, _log_for("kandidaten"))
        st.session_state["scan_candidates"] = candidates
        _step("kandidaten", "complete", done=len(signals),
              detail=f"{len(candidates)} passende Signale aus {len(signals)}")
        return candidates

    def _run_forensik(candidates: list[dict], cfg) -> None:
        n_export = min(len(candidates), cfg["top_n_export"])
        if not n_export:
            _step("forensik", "skipped", detail="Keine passenden Signale nach der Auswahl")
            return
        session = pipeline.Mql5Session(cfg)
        log = _log_for("forensik")
        if not session.has_credentials:
            log("Kein MQL5-Login — nur Kennzahlen möglich, Trade-Exporte entfallen "
                "(Vorprüfung). Login unter Einstellungen ergänzen.")
        else:
            _step("forensik", detail="MQL5-Anmeldung prüfen …")
            try:
                from mqlkiscanner.mql5.browser_session import ensure_mql5_cookies
                if not ensure_mql5_cookies(cfg, session, log=log):
                    raise RuntimeError(
                        "Login über Browser nicht bestätigt — Zugangsdaten unter "
                        "Einstellungen prüfen.")
            except Exception as exc:
                _step("forensik", "error", total=n_export,
                      detail=f"MQL5-Login fehlgeschlagen: {exc}")
                return
        _step("forensik", "running", total=n_export,
              detail="Handelsdaten laden, speichern und prüfen …")
        stopped_early = False
        for i, candidate in enumerate(candidates[:n_export]):
            _step("forensik", done=i,
                  detail=f"Signal {i + 1}/{n_export}: {candidate.get('name')} #{candidate['id']}")
            try:
                result = pipe.analyze_candidate(session, candidate, log)
                st.session_state.scan_results.append(result)
            except pipeline.Mql5HardStopError as exc:
                if getattr(exc, "result", None) is not None:
                    st.session_state.scan_results.append(exc.result)
                log(str(exc))
                skipped = n_export - (i + 1)
                if skipped > 0:
                    log(f"Fail-Fast: {skipped} weitere Signale nicht mehr von MQL5 geholt.")
                stopped_early = True
                _step("forensik", done=i + 1)
                break
            _step("forensik", done=i + 1)
        results = st.session_state.scan_results
        good = sum(r.forensik_vorhanden and not r.fehler for r in results)
        errors = sum(bool(r.fehler) for r in results)
        preview = len(results) - good - errors
        if stopped_early:
            _step("forensik", "warning",
                  detail=(f"Abbruch zum Account-Schutz · {good} geprüft · "
                          f"{preview} Vorprüfung · {errors} Fehler"))
        else:
            _step(
                "forensik",
                "complete" if good == len(results) else "error" if errors == len(results) else "warning",
                detail=f"{good} gründlich geprüft · {preview} nur Vorprüfung · {errors} mit Fehlern",
            )

    try:
        if mode in ("local", "llm", "step_llm", "step_forensik", "step_kandidaten"):
            for sid in ("listen", "kandidaten"):
                if mode in ("local", "llm") or (
                        sid == "listen" and mode == "step_kandidaten"
                        and not st.session_state.get("scan_signals")):
                    _step(sid, "skipped", detail="Vorhandene Daten verwenden")
        if mode == "local":
            _step("llm", "skipped", detail="Lokaler Lauf ohne neuen KI-Aufruf")
            files = sorted(config.RAW_DIR.glob("*.csv")) + sorted(config.RAW_DIR.glob("*.json"))
            if not files:
                _step("forensik", "skipped", detail="Keine Testdateien in data/raw vorhanden")
            else:
                log = _log_for("forensik")
                _step("forensik", "running", total=len(files),
                      detail="Lokale Testdateien werden geprüft")
                for i, file in enumerate(files):
                    _step("forensik", detail=f"Datei {i + 1}/{len(files)}: {file.name}", done=i)
                    rows = pipeline.ScanPipeline.analyze_local_files([str(file)], run_config)
                    st.session_state.scan_results.extend(rows)
                    log(f"{file.name}: " + ("Fehler" if any(r.fehler for r in rows) else "analysiert"))
                    _step("forensik", done=i + 1)
                good = sum(r.forensik_vorhanden and not r.fehler for r in st.session_state.scan_results)
                bad = len(st.session_state.scan_results) - good
                _step(
                    "forensik",
                    "complete" if not bad else "warning" if good else "error",
                    detail=f"{good} Dateien geprüft · {bad} fehlerhaft",
                )
        elif mode == "llm":
            _step("forensik", "skipped", detail="Vorliegende Prüfergebnisse verwenden")
            _run_llm(st.session_state.scan_results, run_config)
        elif mode == "step_listen":
            _run_listen(run_config)
        elif mode == "step_kandidaten":
            signals = st.session_state.get("scan_signals")
            if not signals:
                _step("kandidaten", "skipped", detail="Erst Station 1 starten (Signale laden)")
            else:
                _step("listen", "complete", detail=f"{len(signals)} Signale aus Station 1 vorhanden")
                _run_kandidaten(signals, run_config)
        elif mode == "step_forensik":
            candidates = st.session_state.get("scan_candidates")
            if not candidates:
                _step("forensik", "skipped", detail="Erst Station 2 starten (Auswahl erzeugen)")
            else:
                _step("kandidaten", "complete",
                      detail=f"{len(candidates)} Signale aus Station 2 vorhanden")
                _run_forensik(candidates, run_config)
        elif mode == "step_llm":
            _run_llm(st.session_state.scan_results, run_config)
        else:
            signals = _run_listen(run_config)
            current_step = "kandidaten"
            candidates = _run_kandidaten(signals, run_config)
            current_step = "forensik"
            _run_forensik(candidates, run_config)
            current_step = "llm"
            if run_config["llm_stufe1"] or run_config["llm_stufe2"]:
                _run_llm(st.session_state.scan_results, run_config)
            else:
                _step("llm", "skipped", detail="KI-Berichte für diesen Lauf ausgeschaltet")
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        st.session_state.scan_logs.setdefault(current_step, []).append(f"FEHLER: {message}")
        _step(current_step, "error", detail=message)
        for sid, _, _, _ in STEPS:
            if workflow["steps"][sid]["status"] == "pending":
                _step(sid, "skipped", detail="Nach vorherigem Fehler nicht ausgeführt")
    workflow["activity"] = "Ergebnisse und Protokoll speichern …"
    _refresh_workflow()
    try:
        st.session_state.last_run_file = pipeline.ScanPipeline.save_run(
            st.session_state.scan_results, st.session_state.scan_logs)
        st.session_state.refreshed_signal_ids = [r.id for r in st.session_state.scan_results]
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
            f"{len(st.session_state.scan_results)} Ergebnisse gespeichert. "
            "Unter „Ergebnisse“ können Sie sie vergleichen."
        ))
    workflow["finished_at"] = datetime.now().isoformat(timespec="seconds")
    st.session_state.scan_running = None
    st.rerun()

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
if st.session_state.scan_logs:
    with st.expander("Ablaufprotokoll (technisch)", icon=":material/receipt_long:"):
        for sid, title, _, _ in STEPS:
            lines = st.session_state.scan_logs.get(sid, [])
            if lines:
                st.markdown(f"**{title}**")
                st.code("\n".join(lines), language=None, wrap_lines=True)
