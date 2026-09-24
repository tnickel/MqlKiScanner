# -*- coding: utf-8 -*-
"""Seite „Automatik" — Zeitplan des Agenten-Daemons je Job einstellen.

Muster Goldscanner (Konfiguration → Automatik): Wochentag + Uhrzeit je
Job, Daemon-Status mit Start/Stopp oben. Der Daemon liest den Plan je
Tick neu (≤ 30 s) — Änderungen greifen ohne Neustart. Ohne eigene
Eingabe gilt das bisherige Taktverhalten (werktags zur Startzeit,
Chef/Teilscan sonntags, Full-Scan am ersten Werktag).
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config
from mqlkiscanner.agenten import daemon, journal, scheduler
from mqlkiscanner.ui_design import apply_theme, info_button, page_header

apply_theme()

page_header(
    "KONFIGURATION · AUTOMATIK", "Automatik",
    "Was der Agenten-Daemon von selbst tut — und wann. Wochentag und "
    "Uhrzeit stellst du hier je Job ein; der Daemon übernimmt Änderungen "
    "im nächsten Tick (≤ 30 s), ein Neustart ist nicht nötig.",
)

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption("Der Daemon muss laufen, damit etwas von selbst passiert. "
               "Konfiguration der Rollen-Inhalte: Einstellungen → Agenten.")
    info_button("automatik", key="automatik_page_help")

# ── Daemon ────────────────────────────────────────────────────────────────
st.subheader("Daemon", width="content")
stat = daemon.status()
d1, d2 = st.columns([2, 1], gap="small", vertical_alignment="center")
with d1:
    if stat["aktiv"]:
        st.badge(f"läuft · PID {stat['pid']}", color="green",
                 icon=":material/monitor_heart:")
        st.caption(f"Tick vor {stat['alter_s']} s · gestartet "
                   f"{stat['gestartet']}")
    else:
        st.badge("gestoppt — ohne Daemon läuft nichts von selbst",
                 color="orange", icon=":material/stop_circle:")
        if stat["letzter_tick"]:
            st.caption(f"letzter Tick: {stat['letzter_tick']}")
with d2:
    if st.button("Daemon starten", icon=":material/play_arrow:",
                 disabled=stat["aktiv"], type="primary",
                 help="Startet den Daemon als eigenen Prozess und erteilt "
                      "die Freigabe (idempotent — läuft er schon, passiert "
                      "nichts)."):
        ergebnis = daemon.starten()
        if ergebnis.get("gestartet"):
            st.toast("Daemon gestartet (unabhängiger Prozess)",
                     icon=":material/check_circle:")
        else:
            st.toast(ergebnis.get("grund", "Läuft bereits."),
                     icon=":material/info:")
        st.rerun()
    if st.button("Daemon stoppen", icon=":material/stop_circle:",
                 disabled=not stat["aktiv"],
                 help="Kooperativer Stopp: Der Daemon beendet sich beim "
                      "nächsten Tick von selbst (≤ 30 s)."):
        daemon.stoppen()
        st.toast("Stopp-Signal gesetzt — Daemon beendet sich (≤ 30 s)",
                 icon=":material/check_circle:")
        st.rerun()

# ── Zeitplan ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Zeitplan", width="content")
st.caption("Ohne eigene Eingabe gilt der eingetragene Standard. Basis der "
           "abgeleiteten Zeiten ist die Startzeit aus Einstellungen → "
           "Agenten (Standard 06:30).")


def _modus_anzeige(modus: str) -> str:
    if modus == "werktags":
        return "Werktags"
    if modus == "taeglich":
        return "Täglich"
    if modus == "monatserster":
        return "Monatserster"
    return modus.capitalize()


def _normalisiere(anzeige: str) -> str:
    """Anzeige-Wort → Scheduler-Modus (Gegenstück zu _modus_anzeige)."""
    wert = anzeige.strip().lower().replace("ä", "ae")
    return wert


def _minute_als_zeit(minute: int):
    from datetime import time
    minute %= 24 * 60
    return time(hour=minute // 60, minute=minute % 60)


# jobs: (Titel, Beschreibung, Tag editierbar?, Zusatz-Hinweis)
JOBS = [
    ("dirigent", "Dirigent", "Plant den Tag: Lagestatus, Code-Plan, "
     "optionale LLM-Randentscheidung", True, ""),
    ("markt", "Marktbeobachter", "Kursdaten + Kennzahlen zu den beobachteten "
     "Symbolen", True, ""),
    ("betreuer", "Betreuer", "Prüft bei jedem 🟢/🟡-Signal, ob der Anbieter "
     "noch so tradet wie früher (Stilbruch-Erkennung)", True, ""),
    ("melder", "Melder (Tagesdigest)", "Tages-Zusammenfassung ins Postfach; "
     "startet erst, wenn der Betreuer fertig ist", True, ""),
    ("chef", "Chefermittler", "Wochen-/Monats-Lagebericht ins Postfach; "
     "zusätzlich am Full-Scan-Tag nach dem Scan", True, ""),
    ("teilscan", "Autonomer Teilscan", "Scannt nur die aktuell 🟢/🟡-Signale "
     "mit allen KI-Stufen", True, ""),
    ("fullscan", "Autonomer Full-Scan", "Kompletter Scan aller Signale — "
     "schwer, deshalb mit festem Monatstermin", False, ""),
]

settings = config.load_settings()
aenderungen: dict = {}
with st.container(border=True):
    for job, titel, beschreibung, tag_editierbar, hinweis in JOBS:
        modus, minute = scheduler.job_termin(settings, job)
        c1, c2, c3 = st.columns([2.1, 1, 1], gap="small",
                                vertical_alignment="center")
        with c1:
            st.markdown(f"**{titel}**")
            st.caption(beschreibung + (f" · {hinweis}" if hinweis else ""))
        with c2:
            if not tag_editierbar:
                st.markdown("1. Werktag im Monat")
            else:
                aktueller_tag = _modus_anzeige(modus)
                if aktueller_tag not in scheduler.TAG_AUSWAHL:
                    aktueller_tag = "Werktags"
                neuer_tag = st.selectbox(
                    "Tag", scheduler.TAG_AUSWAHL,
                    index=scheduler.TAG_AUSWAHL.index(aktueller_tag),
                    key=f"automatik_tag_{job}", label_visibility="collapsed")
                if _normalisiere(neuer_tag) != modus:
                    aenderungen[f"agenten_{job}_tag"] = neuer_tag
        with c3:
            widget = st.time_input("Uhrzeit",
                                   value=_minute_als_zeit(minute),
                                   key=f"automatik_zeit_{job}",
                                   label_visibility="collapsed",
                                   step=timedelta(minutes=1))
            zeile = f"{widget.hour:02d}:{widget.minute:02d}"
            if zeile != f"{minute // 60:02d}:{minute % 60:02d}":
                aenderungen[f"agenten_{job}_zeit"] = zeile

if aenderungen:
    if st.button("Zeitplan speichern", key="automatik_speichern",
                 type="primary",
                 icon=":material/save:",
                 help="Der Daemon liest den Zeitplan im nächsten Tick neu "
                      "(≤ 30 s) — ein Neustart ist nicht nötig."):
        config.save_settings({**config.load_settings(), **aenderungen})
        st.toast("Zeitplan gespeichert — Daemon übernimmt automatisch",
                 icon=":material/check_circle:")
        st.rerun()
    st.info("Ungespeicherte Änderungen: " + ", ".join(
        f"{k.removeprefix('agenten_')} = {v}" for k, v in aenderungen.items()))
else:
    st.caption("Alles beim Standard — zum Ändern Wochentag oder Uhrzeit "
               "verstellen und speichern.")

# ── Letzte Läufe ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Letzte Daemon-Läufe", width="content")
letzte = journal.list_laeufe(limit=8)
if letzte:
    for lauf in letzte:
        symbol = "✓" if lauf.get("status") == "ok" else "·"
        st.markdown(f"{str(lauf.get('start', ''))[:16]} · "
                    f"{lauf.get('rolle', '?')} · {symbol} "
                    f"{lauf.get('status', '')}")
    st.caption("Volles Schritt-Protokoll: Seite „Agenten“ → Protokoll.")
else:
    st.caption("Noch keine Daemon-Läufe.")
