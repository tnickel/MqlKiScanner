# -*- coding: utf-8 -*-
"""MqlKiScanner — Streamlit-App (Phase 4, doc/04_roadmap.md).

Einstiegspunkt: Navigation + globaler Status. Business-Logik liegt in
src/mqlkiscanner/ (Engine, Pipeline, MQL5-Zugriff, LLM) — die Seiten sind
duenn.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

from mqlkiscanner import config, downloader_sync, secrets_store  # noqa: E402
from mqlkiscanner.ui_design import apply_theme, info_button  # noqa: E402

st.set_page_config(
    page_title="MqlKiScanner",
    page_icon=":material/radar:",
    layout="wide",
)
apply_theme()

# ------------------------------------------------------------- Session-State
defaults = {
    "scan_results": [],        # list[ScanResult]
    "scan_logs": {},           # step_id -> list[str]
    "scan_running": None,      # aktueller Schritt (fuer Statusanzeige)
    "last_run_file": None,
    "refreshed_signal_ids": None,  # unbekannter Altstand; [] = explizit nichts aktualisiert
    "portfolio_bericht": "",   # Station 5: globaler KI-Portfolio-Vorschlag
}
for key, val in defaults.items():
    st.session_state.setdefault(key, val)

# Shared page objects keep navigation and in-app links in sync.
scan_page = st.Page("app_pages/scan.py", title="Scan", icon=":material/radar:")
results_page = st.Page(
    "app_pages/ergebnisse.py", title="Ergebnisse", icon=":material/table_chart:"
)
settings_page = st.Page(
    "app_pages/admin.py", title="Einstellungen", icon=":material/settings:"
)

# ------------------------------------------------------------------ Sidebar
status = secrets_store.secret_status()
settings = config.load_settings()
emblem_path = ROOT / "assets" / "brand_emblem.jpg"
if emblem_path.exists():
    st.logo(str(emblem_path), size="large")
with st.sidebar:
    with st.container(key="sidebar_brand", gap="xsmall"):
        st.caption("SIGNAL RESEARCH · FORENSIC RADAR")
        st.header("MqlKiScanner")
        st.caption("Risiko vor Ertrag")
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**Systemstatus**")
            info_button("connections", key="sidebar_connections")
        mql_ready = status["mql5_user"] and status["mql5_pass"]
        st.badge("MQL5 bereit" if mql_ready else "MQL5-Zugang fehlt",
                 color="green" if mql_ready else "orange", icon=":material/person:")
        st.badge("KI bereit" if status["glm_api_key"] else "KI optional",
                 color="green" if status["glm_api_key"] else "gray", icon=":material/psychology:")
        # Erreichbarkeit des MqlDownloader: einmal beim Programmstart geprüft,
        # danach 5 Min. gecacht (verbindungs_status verhindert REST-Flut).
        dl_status = downloader_sync.verbindungs_status(timeout=3.0)
        if not dl_status["konfiguriert"]:
            st.badge("Downloader optional", color="gray", icon=":material/sync:")
        elif dl_status["ok"]:
            st.badge("Downloader verbunden", color="green", icon=":material/sync:")
            st.caption(f"{dl_status['providers']} Provider · geprüft "
                       f"{dl_status['geprueft']:%H:%M}")
        else:
            st.badge("Downloader offline", color="red", icon=":material/sync_disabled:")
            st.page_link(settings_page, label="Verbindung prüfen",
                         icon=":material/arrow_forward:")
        if not mql_ready:
            st.page_link(settings_page, label="Zugang einrichten",
                         icon=":material/arrow_forward:")
    with st.container(border=True):
        st.caption("ENTSCHEIDUNGSREGEL")
        st.markdown("**≤ 30 % Drawdown**  \n**> 5 % Ertrag / Monat**")
        st.caption("Ein Stop zählt nur, wenn er belegt ist.")
    if st.session_state.last_run_file:
        st.caption(f"Letzter Lauf · {Path(st.session_state.last_run_file).parent.name}")

# --------------------------------------------------------------- Navigation
page = st.navigation(
    {
        "Arbeitsbereich": [
            scan_page,
            results_page,
        ],
        "Konfiguration": [
            settings_page,
        ],
    },
    position="sidebar",
)
page.run()
