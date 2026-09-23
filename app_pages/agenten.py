# -*- coding: utf-8 -*-
"""Seite „Agenten" — das Fenster zum autonomen Betrieb (Phase A, doc/19).

Zwei Bereiche: Live (was läuft gerade, letzte Läufe, Daemon-Status) und
Protokoll (jeder Schritt chronologisch; LLM-Schritte aufklappbar bis zum
vollständigen Prompt und vollständiger Antwort — „alles, was ein LLM
sagt, steht im Protokoll", Nutzer-Vorgabe statt Trockenmodus).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config
from mqlkiscanner.agenten import daemon, journal, rollen
from mqlkiscanner.ui_design import action_button, apply_theme, info_button, \
    page_header

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

live_tab, protokoll_tab, dossiers_tab, postfach_tab = st.tabs(
    ["Live", "Protokoll", "Dossiers", "Postfach"])

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

        # Sperre, solange irgendein Agentenlauf aktiv ist (GUI-Kette,
        # Einzelstart oder Daemon-Takt): Ein weiterer Klick würde nichts
        # parallel starten (Lock), aber Tokens doppelt verbrauchen. Auch
        # gepufferte Klicks während des blockierten Skripts laufen so ins
        # Leere statt eine zweite Kette anzustoßen.
        lauf_aktiv = bool(journal.aktive_rollen()) or bool(
            st.session_state.get("agenten_komplett_lauf")
            or st.session_state.get("aktiver_agent_lauf"))
        if action_button(
                "Kompletten Agenten-Workflow jetzt ausführen",
                key="agenten_komplett_start", type="primary",
                help_key="agenten_komplett_start",
                icon=":material/rocket_launch:", disabled=lauf_aktiv):
            st.session_state["agenten_komplett_lauf"] = True
            st.rerun()
        if lauf_aktiv:
            st.caption("⏳ Ein Agentenlauf ist aktiv — der Button ist gesperrt, "
                       "bis er beendet ist (Meldungen und Verlauf laufen live "
                       "im Kasten darunter bzw. unter „Letzte Läufe“).")
        else:
            st.caption("Ein Klick, die ganze Tageskette: Ampelwechsel-Prüfung → "
                       "Dirigent → Markt → Betreuer → Tagesdigest. Chefermittler "
                       "und autonome Scans bleiben an ihre Takte gebunden "
                       "(Sonntag/Monatsbeginn).")

    from mqlkiscanner.agenten import ui_tree
    ui_tree.rendere_agenten_baum()

    with st.container(border=True):
        st.markdown("**Letzte Läufe**")
        laeufe = journal.list_laeufe(limit=15)
        if not laeufe:
            st.caption("Noch keine Läufe — der Dirigent schreibt hier, sobald der "
                       "Betrieb läuft (oder per Kommandozeile: "
                       "`PYTHONPATH=src python -m mqlkiscanner.agenten --once`).")
        else:
            def _rolle_label(r_key: str) -> str:
                icons = {
                    "dirigent": "🎼 Dirigent",
                    "markt": "📊 Markt",
                    "betreuer": "🛡️ Betreuer",
                    "chef": "🕵️ Chef",
                    "melder": "📬 Melder",
                }
                return icons.get(r_key, r_key.capitalize())

            def _status_label(s: str) -> str:
                sl = (s or "").lower()
                if sl == "ok":
                    return "✅ OK"
                if sl == "skipped":
                    return "⏭️ Übersprungen"
                if sl == "fehler":
                    return "❌ Fehler"
                if sl == "laeuft":
                    return "⏳ Läuft..."
                return s.upper()

            tabelle_daten = [
                {
                    "Zeit": lauf["start"],
                    "Rolle": _rolle_label(lauf["rolle"]),
                    "Aktion": lauf.get("aktion") or "—",
                    "Resultat": lauf.get("resultat") or lauf.get("zusammenfassung") or "—",
                    "Status": _status_label(lauf["status"]),
                    "Quelle": lauf["quelle"].upper(),
                }
                for lauf in laeufe
            ]
            st.dataframe(
                tabelle_daten,
                column_config={
                    "Zeit": st.column_config.TextColumn("Zeit", width="small"),
                    "Rolle": st.column_config.TextColumn("Rolle", width="small"),
                    "Aktion": st.column_config.TextColumn("Was wurde gemacht?", width="medium"),
                    "Resultat": st.column_config.TextColumn("Was war das Resultat?", width="large"),
                    "Status": st.column_config.TextColumn("Status", width="small"),
                    "Quelle": st.column_config.TextColumn("Quelle", width="small"),
                },
                width="stretch", hide_index=True)

            with st.expander("🔍 Technische Details zu einem Lauf anzeigen", expanded=False):
                auswahl_lauf_id = st.selectbox(
                    "Lauf zur Detailansicht auswählen",
                    [l["id"] for l in laeufe],
                    format_func=lambda lid: next(
                        f"#{l['id']} · {l['start']} · {_rolle_label(l['rolle'])} [{l['status']}]"
                        for l in laeufe if l["id"] == lid),
                    key="agenten_letzte_laeufe_sel"
                )
                if auswahl_lauf_id:
                    sel = next(l for l in laeufe if l["id"] == auswahl_lauf_id)
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**Durchgeführte Aktion:**\n{sel.get('aktion') or '—'}")
                        st.caption(f"Rolle: `{sel['rolle']}` · Quelle: `{sel['quelle']}` · Signal-ID: `{sel.get('signal_id') or '—'}`")
                    with c2:
                        st.markdown(f"**Fachliches Resultat:**\n{sel.get('resultat') or '—'}")
                        st.caption(f"Start: `{sel['start']}` · Ende: `{sel.get('ende') or '—'}` · Status: `{sel['status']}`")
                    if sel.get("zusammenfassung"):
                        st.caption(f"System-Meldung: `{sel['zusammenfassung']}`")

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
              "Token": int(s["tokens"] or 0),
              "Dauer (s)": f"{s['dauer_s']:.2f}" if s.get("dauer_s") is not None else "—"}
             for s in schritte],
            width="stretch", hide_index=True)
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
                       width="stretch", hide_index=True)
                else:
                    st.caption("Noch keine Deltas — der erste Tageslauf mit "
                               "geändertem Export erzeugt den ersten Eintrag.")

# ── Postfach (Phase D) ─────────────────────────────────────────────
with postfach_tab:
    st.markdown(
        "Alerts und Digests des Melders. Priorität: **1 Info** · "
        "**2 Warnung** · **3 Kritisch**. Jede Meldung nennt ihre Quellen "
        "(Protokoll-Schritt, Ampel-Wechsel, Signal).")
    filter_spalte, leer_spalte = st.columns([1, 2])
    with filter_spalte:
        meldungs_typ = st.selectbox(
            "Art", ["alle", "alert", "digest", "lagebericht", "scan"],
            key="agenten_postfach_typ")
    meldungen = journal.meldungen_lesen(
        limit=50, typ=None if meldungs_typ == "alle" else meldungs_typ)
    if not meldungen:
        st.caption("Postfach leer — der Melder schreibt Alerts bei "
                   "Ampelwechseln und Stilbrüchen, dazu den Tagesdigest.")
    for m in meldungen:
        farbe = {3: "red", 2: "orange", 1: "blue"}.get(m["prioritaet"], "gray")
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center",
                              wrap=True):
                st.badge(f"P{m['prioritaet']}", color=farbe)
                st.badge(m["typ"], color="gray")
                st.caption(m["ts"])
            st.markdown(f"**{m['titel']}**")
            st.markdown(m["text"])
            if m.get("quellen"):
                st.caption("Quellen: " + ", ".join(
                    f"`{q}`" for q in m["quellen"]))
