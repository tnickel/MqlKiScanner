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

from mqlkiscanner import config, secrets_store  # noqa: E402
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
    "refreshed_signal_ids": [],
    "portfolio_bericht": "",   # Station 5: globaler KI-Portfolio-Vorschlag
}
for key, val in defaults.items():
    st.session_state.setdefault(key, val)

# ------------------------------------------------------------------ Sidebar
status = secrets_store.secret_status()
settings = config.load_settings()
with st.sidebar:
    with st.container(key="sidebar_brand", gap="xsmall"):
        emblem_path = ROOT / "assets" / "brand_emblem.jpg"
        if emblem_path.exists():
            st.image(str(emblem_path), use_container_width=True)
        st.caption("SIGNAL RESEARCH · FORENSIC RADAR")
        st.header("MqlKiScanner", icon=":material/radar:")
        st.markdown("**Risiko vor Ertrag.**")
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown("**Verbindungen**")
            info_button("connections", key="sidebar_connections")
        mql_ready = status["mql5_user"] and status["mql5_pass"]
        st.badge("MQL5 · hinterlegt" if mql_ready else "MQL5 · unvollständig",
                 color="green" if mql_ready else "orange", icon=":material/person:")
        st.badge("KI-Key · hinterlegt" if status["glm_api_key"] else "KI · optional, Key fehlt",
                 color="green" if status["glm_api_key"] else "gray", icon=":material/psychology:")
        st.caption("Hinterlegte Zugänge sind noch kein Verbindungstest.")
    with st.container(border=True):
        st.caption("PRÜFPRINZIP")
        st.markdown("**Schutz muss belegt sein.**")
        st.caption("Drawdown · Exposure · Stop-Nachweis")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("Workflow in Kurzform")
        info_button("workspace", key="sidebar_guide")
    st.caption("Daten holen → speichern → prüfen → KI-Bericht → Portfolio-Vorschlag")
    if st.session_state.last_run_file:
        st.caption(f"Letzter Lauf · {Path(st.session_state.last_run_file).parent.name}")

# --------------------------------------------------------------- Navigation
page = st.navigation(
    {
        "Arbeitsbereich": [
            st.Page("app_pages/scan.py", title="Scan", icon=":material/radar:"),
            st.Page("app_pages/ergebnisse.py", title="Ergebnisse", icon=":material/table_chart:"),
        ],
        "Konfiguration": [
            st.Page("app_pages/admin.py", title="Einstellungen", icon=":material/settings:"),
        ],
    },
    position="sidebar",
)
page.run()
