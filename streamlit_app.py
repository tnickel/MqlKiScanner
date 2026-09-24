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

from mqlkiscanner import config, downloader_sync, secrets_store, tradeserver_sync, rest_api  # noqa: E402
from mqlkiscanner.ui_design import apply_theme, info_button  # noqa: E402

st.set_page_config(
    page_title="MqlKiScanner",
    page_icon=":material/radar:",
    layout="wide",
)
apply_theme()


@st.cache_resource(show_spinner=False)
def _rest_api_server():
    """Schreibgeschütztes REST-Interface (MqlRealMonitor) — einmal je Prozess."""
    try:
        return rest_api.start_background()
    except Exception:  # App läuft auch ohne REST weiter (z. B. Port belegt)
        return None


rest_server = _rest_api_server()

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
agenten_page = st.Page(
    "app_pages/agenten.py", title="Agenten", icon=":material/tune:"
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
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Arbeitsbereich — was macht was?**")
        info_button("arbeitsbereich", key="sidebar_arbeitsbereich")
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
        # Tradeserver (MqlTradeMonitor): Einmal-Sync-Ziel für Tabelle + PDFs.
        ts_status = tradeserver_sync.verbindungs_status(timeout=3.0)
        if not ts_status["konfiguriert"]:
            st.badge("Tradeserver optional", color="gray", icon=":material/cloud_upload:")
        elif ts_status["ok"]:
            st.badge("Tradeserver verbunden", color="green", icon=":material/cloud_upload:")
            st.caption(f"{ts_status['service'] or 'MqlTradeMonitor'} · geprüft "
                       f"{ts_status['geprueft']:%H:%M}")
        else:
            st.badge("Tradeserver nicht erreichbar", color="red",
                     icon=":material/cloud_off:")
            st.page_link(settings_page, label="Verbindung prüfen",
                         icon=":material/arrow_forward:")
        # REST-Interface für den MqlRealMonitor (nur lesend, localhost).
        # Der Monitor ruft nur auf Knopfdruck ab — der Badge zeigt deshalb,
        # wann der Client zuletzt erreicht hat (grün ab erstem Abruf).
        if rest_server is not None:
            _rs_port = rest_server.server_address[1]
            _cs = rest_api.client_status()
            if _cs["verbunden"]:
                st.badge(f"REST-Server :{_rs_port} · Client zuletzt "
                         f"{_cs['letzter_abruf']:%H:%M}",
                         color="green", icon=":material/cable:")
            else:
                st.badge(f"REST-Server :{_rs_port} · noch kein Client",
                         color="gray", icon=":material/cable:")
        elif config.load_settings().get("rest_api_enabled", True):
            st.badge("REST-API Port belegt", color="orange",
                     icon=":material/cable:")
        else:
            st.badge("REST-API aus", color="gray", icon=":material/cable:")
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
            agenten_page,
        ],
        "Konfiguration": [
            settings_page,
        ],
    },
    position="sidebar",
)
page.run()
