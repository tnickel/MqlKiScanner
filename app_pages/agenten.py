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
    f"AUTONOMER BETRIEB · PHASE {rollen.AKTUELLE_PHASE}", "Agenten",
    "Fünf LLM-Rollen beobachten die Signale — jeder Schritt lückenlos "
    "protokolliert, jede Modelläußerung nachlesbar.",
    image_path=str(agenten_banner) if agenten_banner.exists() else None,
)
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption("Die Engine bewertet — Agenten beobachten und melden. "
               "Konfiguration: Einstellungen → Agenten.")
    info_button("agenten_page", key="agenten_page_help")

live_tab, protokoll_tab, dossiers_tab = st.tabs(["Live", "Protokoll", "Dossiers"])

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
        for rolle in rollen.ROLLEN:
            with st.container(horizontal=True, vertical_alignment="center", wrap=True):
                st.markdown(f"{rolle.icon} **{rolle.name}** — {rolle.takt}")
                if rollen.phase_aktiv(rolle, rollen.AKTUELLE_PHASE):
                    st.badge(f"Phase {rolle.phase} · aktiv", color="green",
                             icon=":material/check_circle:")
                else:
                    st.badge(f"Phase {rolle.phase} · geplant", color="orange",
                             icon=":material/history:")
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

# ── Dossiers (Phase B) ─────────────────────────────────────────────
with dossiers_tab:
    from mqlkiscanner import db as scanner_db
    from mqlkiscanner.agenten import dossier as dossier_db

    st.markdown(
        "Je Signal die wachsende Datenbasis: **Algo-Profil** (versioniert, aus "
        "Tiefenanalyse/Gesamtbericht destilliert), **Beobachtungen** des "
        "Betreuers und **Trade-Deltas**. Das Profil ist Beobachtungsbasis — "
        "Ampel und Urteil bleiben Engine-Sache.")
    katalog = scanner_db.list_catalog()
    if not katalog:
        st.caption("Keine Signale in der Datenbank — erst einen Scan laufen lassen.")
    else:
        eintraege = [{"id": s["signal_id"], "name": s["name"] or f"#{s['signal_id']}"}
                     for s in katalog]
        auswahl = st.selectbox(
            "Signal", eintraege, format_func=lambda e: e["name"],
            key="agenten_dossier_signal")
        if auswahl:
            signal_id = auswahl["id"]
            profil = dossier_db.profil_lesen(signal_id)
            historie = dossier_db.profil_historie(signal_id)
            beobachtungen = dossier_db.beobachtungen_lesen(signal_id, limit=15)
            deltas = dossier_db.deltas_lesen(signal_id, limit=10)

            if profil is None:
                st.info("Noch kein Algo-Profil — der Betreuer destilliert beim "
                        "nächsten Tageslauf (vorherige Tiefenanalyse/Gesamtbericht "
                        "erforderlich).", icon=":material/history:")
            else:
                with st.container(border=True):
                    with st.container(horizontal=True, vertical_alignment="center",
                                      wrap=True):
                        st.markdown("**Algo-Profil**")
                        st.badge(f"Version {profil['version']}", color="blue",
                                 icon=":material/check:")
                        st.caption(f"destilliert {profil['erstellt']} · "
                                   f"{profil['modell'] or 'Modell unbekannt'}")
                    st.markdown(profil["profil_text"])
                    if len(historie) > 1:
                        with st.expander(f"Profil-Historie ({len(historie) - 1} "
                                         "ältere Versionen)"):
                            for eintrag in historie[1:]:
                                st.caption(f"Version {eintrag['version']} · "
                                           f"{eintrag['erstellt']} · "
                                           f"{eintrag['aenderungs_grund'] or ''}")

            with st.container(border=True):
                st.markdown(f"**Beobachtungen** ({len(beobachtungen)})")
                if not beobachtungen:
                    st.caption("Noch keine — der Betreuer schreibt hier bei jedem "
                               "Tageslauf.")
                for b in beobachtungen[:10]:
                    farbe = {"KONFORM": "green", "KEINE_NEUEN_TRADES": "gray",
                             "AUFFAELLIG": "orange", "STILBRUCH": "red"
                             }.get(b["einordnung"], "gray")
                    with st.container(horizontal=True, vertical_alignment="top",
                                      wrap=True):
                        st.badge(b["einordnung"], color=farbe)
                        st.caption(f"{b['ts']}")
                    st.markdown(b["text"])

            with st.container(border=True):
                st.markdown(f"**Trade-Deltas** ({len(deltas)})")
                if deltas:
                    st.dataframe(
                        [{"Zeit": d["ts"], "Neue Trades": d["neue_trades"],
                          "Hash (neu)": (d["neu_sha256"] or "")[:12] + "…"}
                         for d in deltas],
                        use_container_width=True, hide_index=True)
                else:
                    st.caption("Noch keine Deltas — der erste Tageslauf mit "
                               "geändertem Export erzeugt den ersten Eintrag.")
