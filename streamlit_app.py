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

st.set_page_config(
    page_title="MqlKiScanner",
    page_icon=":material/radar:",
    layout="wide",
)

# ------------------------------------------------------------- Session-State
defaults = {
    "scan_results": [],        # list[ScanResult]
    "scan_logs": {},           # step_id -> list[str]
    "scan_running": None,      # aktueller Schritt (fuer Statusanzeige)
    "last_run_file": None,
}
for key, val in defaults.items():
    st.session_state.setdefault(key, val)

# ------------------------------------------------------------------ Sidebar
st.sidebar.title("MqlKiScanner", icon=":material/radar:")
st.sidebar.caption("MQL5-Signale forensisch pruefen — Risiko vor Ertrag.")

status = secrets_store.secret_status()
chunks = [
    ("GLM-Key", status["glm_api_key"], ":material/key:"),
    ("MQL5-Login", status["mql5_user"], ":material/person:"),
]
for label, ok, icon in chunks:
    st.sidebar.markdown(
        f"{label}: {'🟢 gesetzt' if ok else '🔴 fehlt'}", unsafe_allow_html=False)

settings = config.load_settings()
st.sidebar.caption(
    f"Rate-Limit: {settings['rate_min_interval_s']:.1f}s/Request, "
    f"{settings['rate_pause_zwischen_signalen_s']:.1f}s je Signal | "
    f"Listen: {settings['listen_seiten']} Seiten | Top-{settings['top_n_export']} Exporte")

st.sidebar.divider()
st.sidebar.caption("Scan → Ergebnisse → Admin: Navigation links.")

if st.session_state.last_run_file:
    st.sidebar.caption(f"Letzter Lauf: `{Path(st.session_state.last_run_file).parent.name}`")

# --------------------------------------------------------------- Navigation
page = st.navigation(
    {
        "": [
            st.Page("app_pages/scan.py", title="Scan", icon=":material/radar:"),
            st.Page("app_pages/ergebnisse.py", title="Ergebnisse", icon=":material/table_chart:"),
        ],
        "Admin": [
            st.Page("app_pages/admin.py", title="Einstellungen & Prompts", icon=":material/settings:"),
        ],
    },
    position="sidebar",
)
page.run()
