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

from mqlkiscanner import config, portfolio_statistik, secrets_store, verbindungs_monitor, rest_api  # noqa: E402
from mqlkiscanner.agenten import daemon as agenten_daemon  # noqa: E402
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
alle_signale_page = st.Page(
    "app_pages/alle_signale.py", title="Alle Signale", icon=":material/analytics:"
)
abonnenten_statistik_page = st.Page(
    "app_pages/abonnenten_statistik.py", title="Abonnentenstatistik",
    icon=":material/group_add:",
)
risiko_rechner_page = st.Page(
    "app_pages/risiko_rechner.py", title="Max-Risiko-Rechner",
    icon=":material/monitoring:",
)
faq_page = st.Page(
    "app_pages/faq.py", title="FAQ", icon=":material/help:"
)
settings_page = st.Page(
    "app_pages/admin.py", title="Einstellungen", icon=":material/settings:"
)
automatik_page = st.Page(
    "app_pages/automatik.py",
    title=f"Automatik {agenten_daemon.status_text()}",
    icon=":material/schedule:",
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
        @st.fragment(run_every=2.0)
        def _verbindungen_anzeigen():
            snapshot = verbindungs_monitor.zustand()
            if snapshot["fehler"]:
                st.badge("Verbindungskonfiguration nicht lesbar", color="orange",
                         icon=":material/sync_problem:")
                st.caption("Die Prüfung wird automatisch erneut versucht.")
            if not snapshot["geladen"]:
                if not snapshot["fehler"]:
                    st.badge("Verbindungen werden geprüft", color="gray",
                             icon=":material/sync:")
                return
            verbindungen = snapshot["verbindungen"]
            if not any(v["name"] == "Downloader" for v in verbindungen):
                st.badge("Downloader optional", color="gray", icon=":material/sync:")
            if not any(v["art"] == "tradeserver" for v in verbindungen):
                st.badge("Tradeserver optional", color="gray", icon=":material/cloud_upload:")
            for v in verbindungen:
                ergebnis = v["ergebnis"]
                if ergebnis is None:
                    st.badge(f"{v['name']} wird geprüft", color="gray",
                             icon=":material/sync:")
                    continue
                eingeschraenkt = ergebnis.get("eingeschraenkt", False)
                ok = ergebnis["ok"] and not eingeschraenkt
                text = "verbunden" if ok else (
                    "Token erforderlich" if eingeschraenkt else "nicht erreichbar")
                st.badge(f"{v['name']} {text}",
                         color="green" if ok else ("orange" if eingeschraenkt else "red"),
                         icon=":material/sync:" if ok else ":material/sync_disabled:")
                suffix = " · wird erneut geprüft" if v["prueft"] else ""
                provider = (f"{ergebnis.get('anbieter') or 0} Provider · "
                            if v["art"] == "quelle" and ok else "")
                st.caption(f"{provider}Geprüft {ergebnis['geprueft']:%H:%M}{suffix}")
                if not ok:
                    st.page_link(settings_page, label="Verbindung prüfen",
                                 icon=":material/arrow_forward:")

        _verbindungen_anzeigen()
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
        dd_limit = float(settings.get("schranke_eq_dd_pct", config.DEFAULT_SETTINGS["schranke_eq_dd_pct"]))
        min_return = float(settings.get("min_ertrag_pct_monat", config.DEFAULT_SETTINGS["min_ertrag_pct_monat"]))
        min_calmar = config.min_calmar_jahr(settings)
        st.markdown(f"**≤ {dd_limit:g} % Drawdown**  \n"
                    f"**Jahres-Calmar ≥ {min_calmar:g}**")
        if min_return > 0:
            st.markdown(f"**≥ {min_return:g} % Ertrag / Monat**")
        else:
            st.caption("Absolute Monats-Ertragshürde deaktiviert.")
        st.caption(f"Mindestens {portfolio_statistik.MIN_HISTORIE_MONATE:g} Monate "
                   "Trade-Historie. Calmar auf gemessener Equity inklusive Floating.")
        st.caption("Fehlender SL-Nachweis ist neutral; ein belegter Stop entlastet.")
    if st.session_state.last_run_file:
        st.caption(f"Letzter Lauf · {Path(st.session_state.last_run_file).parent.name}")

# --------------------------------------------------------------- Navigation
page = st.navigation(
    {
        "Arbeitsbereich": [
            scan_page,
            results_page,
            agenten_page,
            alle_signale_page,
            abonnenten_statistik_page,
            risiko_rechner_page,
        ],
        "Konfiguration": [
            settings_page,
            automatik_page,
        ],
        "Hilfe": [
            faq_page,
        ],
    },
    position="sidebar",
)
page.run()
