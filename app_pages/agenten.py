# -*- coding: utf-8 -*-
"""Seite „Agenten" — das Fenster zum autonomen Betrieb (Phase A, doc/19).

Zwei Bereiche: Live (was läuft gerade, letzte Läufe, Daemon-Status) und
Protokoll (jeder Schritt chronologisch; LLM-Schritte aufklappbar bis zum
vollständigen Prompt und vollständiger Antwort — „alles, was ein LLM
sagt, steht im Protokoll", Nutzer-Vorgabe statt Trockenmodus).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config
from mqlkiscanner.agenten import daemon, journal, rollen
from mqlkiscanner.ui_design import apply_theme, info_button, page_header

apply_theme()

agenten_banner = Path(__file__).resolve().parents[1] / "assets" / "hero_agenten_banner.jpg"
page_header(
    "AUTONOMER BETRIEB · PHASE A", "Agenten",
    "Fünf LLM-Rollen beobachten die Signale — jeder Schritt lückenlos "
    "protokolliert, jede Modelläußerung nachlesbar.",
    image_path=str(agenten_banner) if agenten_banner.exists() else None,
)
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption("Die Engine bewertet — Agenten beobachten und melden. "
               "Konfiguration: Einstellungen → Agenten.")
    info_button("agenten_page", key="agenten_page_help")

live_tab, protokoll_tab = st.tabs(["Live", "Protokoll"])

# ── Live ───────────────────────────────────────────────────────────
with live_tab:
    daemon_status = daemon.status()
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", wrap=True):
            if daemon_status["aktiv"]:
                st.badge("Daemon läuft", color="green", icon=":material/play_arrow:")
                st.caption(f"PID {daemon_status['pid']} · Tick vor "
                           f"{daemon_status['alter_s']} s · gestartet "
                           f"{daemon_status['gestartet']}")
            else:
                st.badge("Daemon gestoppt", color="gray",
                         icon=":material/stop_circle:")
                if daemon_status["letzter_tick"]:
                    st.caption(f"letzter Tick: {daemon_status['letzter_tick']}")
            st.badge("Freigabe erteilt" if config.load_settings().get("agenten_enabled")
                     else "Freigabe aus",
                     color="green" if config.load_settings().get("agenten_enabled")
                     else "orange", icon=":material/lock:")
            st.caption("Starten, Stoppen und Konfigurieren: Einstellungen → Agenten")

    with st.container(border=True):
        st.markdown("**Die fünf Rollen**")
        phasen = ["A", "B", "C", "D", "E"]
        for rolle in rollen.ROLLEN:
            with st.container(horizontal=True, vertical_alignment="center", wrap=True):
                st.markdown(f"{rolle.icon} **{rolle.name}** — {rolle.takt}")
                if phasen.index(rolle.phase) > 0:
                    st.badge(f"Phase {rolle.phase} · geplant", color="orange",
                             icon=":material/history:")
                else:
                    st.badge("Phase A · aktiv", color="green",
                             icon=":material/check_circle:")
            st.caption(rolle.beschreibung)

    with st.container(border=True):
        st.markdown("**Letzte Läufe**")
        laeufe = journal.list_laeufe(limit=10)
        if not laeufe:
            st.caption("Noch keine Läufe — der Dirigent schreibt hier, sobald der "
                       "Betrieb läuft (oder per Kommandozeile: "
                       "`PYTHONPATH=src python -m mqlkiscanner.agenten --once`).")
        else:
            st.dataframe(
                [{"Zeit": l["start"], "Rolle": l["rolle"], "Quelle": l["quelle"],
                  "Status": l["status"], "Zusammenfassung": l["zusammenfassung"] or ""}
                 for l in laeufe],
                use_container_width=True, hide_index=True)

# ── Protokoll ──────────────────────────────────────────────────────
with protokoll_tab:
    st.markdown(
        "Jeder Schritt des Betriebs — Code wie LLM. LLM-Schritte speichern den "
        "**vollständigen gefüllten Prompt** und die **vollständige Antwort**; "
        "nichts wird gekürzt.")
    filter_spalte, _leer = st.columns([1, 2])
    with filter_spalte:
        rollen_filter = st.selectbox(
            "Rolle", ["alle"] + [r.key for r in rollen.ROLLEN],
            key="agenten_protokoll_rolle")
        tag_filter = st.date_input("Tag", value=date.today(),
                                   key="agenten_protokoll_tag")
    schritte = journal.list_schritte(
        limit=200,
        rolle=None if rollen_filter == "alle" else rollen_filter,
        tag=tag_filter.strftime("%Y-%m-%d"))
    if not schritte:
        st.caption("Keine Schritte für diese Auswahl.")
    else:
        st.dataframe(
            [{"Zeit": s["ts"], "Rolle": s["rolle"], "Schritt": s["schritt"],
              "Status": s["status"], "Modell": s["modell"] or "—",
              "Token": s["tokens"] or 0,
              "Dauer (s)": s["dauer_s"] if s["dauer_s"] is not None else "—"}
             for s in schritte],
            use_container_width=True, hide_index=True)
        auswahl = st.selectbox(
            "Schritt öffnen (vollständiger Prompt und Antwort bei LLM-Schritten)",
            [s["id"] for s in schritte],
            format_func=lambda sid: next(
                f"#{s['id']} · {s['ts']} · {s['rolle']}/{s['schritt']} ({s['status']})"
                for s in schritte if s["id"] == sid),
            key="agenten_protokoll_auswahl")
        if auswahl:
            detail = journal.schritt_lesen(auswahl)
            if detail:
                with st.expander(f"Schritt #{detail['id']} — {detail['schritt']}",
                                 expanded=True):
                    if detail.get("detail"):
                        st.json(detail["detail"])
                    if detail.get("prompt"):
                        st.markdown("**Gesendeter Prompt (vollständig)**")
                        st.text_area("prompt", value=detail["prompt"], height=220,
                                     disabled=True, label_visibility="collapsed",
                                     key=f"agenten_prompt_view_{auswahl}")
                    if detail.get("antwort"):
                        st.markdown("**Antwort des Modells (vollständig)**")
                        st.text_area("antwort", value=detail["antwort"], height=220,
                                     disabled=True, label_visibility="collapsed",
                                     key=f"agenten_antwort_view_{auswahl}")
