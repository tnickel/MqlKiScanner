# -*- coding: utf-8 -*-
"""Ergebnisse-Seite: Ampel-Metriken, Gesamttabelle, Detailansicht."""
from __future__ import annotations

import json
from pathlib import Path

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from mqlkiscanner import config, pipeline
from mqlkiscanner.app_ui import render_detail, render_results_table

st.title("Ergebnisse", icon=":material/table_chart:")

# Letzten Lauf nachladen, wenn die Session leer ist (App-Neustart)
if not st.session_state.scan_results and st.session_state.last_run_file:
    path = Path(st.session_state.last_run_file)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        st.session_state.scan_results = [
            pipeline.ScanResult(**{k: v for k, v in row.items() if k in pipeline.ScanResult.__dataclass_fields__})
            for row in data.get("ergebnisse", [])
        ]

runs = sorted(config.RUNS_DIR.glob("*/results.json"), reverse=True)
selected_run = st.selectbox(
    "Lauf",
    options=["(aktueller Lauf / Session)"] + [str(p) for p in runs[:12]],
    format_func=lambda p: p if p == "(aktueller Lauf / Session)"
    else Path(p).parent.name,
)
if (selected_run != "(aktueller Lauf / Session)"
        and Path(selected_run) != Path(st.session_state.last_run_file or "")):
    data = json.loads(Path(selected_run).read_text(encoding="utf-8"))
    st.session_state.scan_results = [
        pipeline.ScanResult(**{k: v for k, v in row.items() if k in pipeline.ScanResult.__dataclass_fields__})
        for row in data.get("ergebnisse", [])
    ]
    st.session_state.last_run_file = selected_run

results = st.session_state.scan_results
if not results:
    st.info("Keine Ergebnisse vorhanden. Auf der Scan-Seite starten oder die "
            "Verifikations-Datensätze laden.")
    st.stop()

ampeln = [r.ampel for r in results]
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Datensätze", len(results))
c2.metric("🟢 Kandidaten", ampeln.count("🟢"))
c3.metric("🟡 Beobachtung", ampeln.count("🟡"))
c4.metric("🔴 Schranke/Flag", ampeln.count("🔴"))
c5.metric("⛔ Ausgeschlossen", ampeln.count("⛔"))
c6.metric("⚪ Vorprüfung", ampeln.count("⚪"))

st.divider()
st.subheader("Gesamttabelle", icon=":material/grid_on:")
sel_id = render_results_table(results, key="ergebnisse_table")

filter_ampel = st.pills("Filter", ["🟢", "🟡", "🔴", "⛔", "⚪"], selection_mode="multi")
if filter_ampel:
    visible = [r for r in results if r.ampel in filter_ampel]
else:
    visible = results

st.divider()
if sel_id is not None:
    selected = next((r for r in results if r.id == sel_id), None)
    if selected:
        render_detail(selected)

st.subheader("Urteile im Überblick", icon=":material/summarize:")
for r in visible:
    with st.container(border=True, horizontal=True):
        st.markdown(f"**{r.ampel} {r.name}** (#{r.id})")
        st.caption(f"{r.urteil}")
