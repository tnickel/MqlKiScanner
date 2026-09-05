# -*- coding: utf-8 -*-
"""Gemeinsame UI-Bausteine fuer die Streamlit-Seiten (Tabelle + Detail)."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from mqlkiscanner.ui_design import action_button, info_button, section_header


def results_to_dataframe(results) -> pd.DataFrame:
    rows = [r.to_row() for r in results]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["Bericht"] = ":material/description: Bericht"
    return df


def render_results_table(results, key: str = "results_table", compact: bool = True) -> int | None:
    """Tabelle mit Ampel- und Bericht-Button; Rueckgabe = gewaehlte Signal-ID."""
    df = results_to_dataframe(results)
    if df.empty:
        st.info("Noch keine Ergebnisse — erst einen Scan starten oder die "
                "Verifikations-Datensaetze laden.")
        return None
    df["Link"] = [f"https://www.mql5.com/en/signals/{r.id}" if r.id else "" for r in results]

    def _open_report():
        click = st.session_state.get(f"{key}_bericht")  # ButtonColumn-Click-Info
        if click is not None and getattr(click, "row", None) is not None:
            st.session_state["report_signal_id"] = results[click.row].id

    event = st.dataframe(
        df,
        key=key,
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
        column_order=(["Ampel", "Name", "EQ-DD %", "Trading-DD %", "Ertrag/Monat %",
                       "Stop", "Score", "Urteil", "Bericht", "Link"] if compact else None),
        column_config={
            "Ampel": st.column_config.TextColumn("", width="small"),
            "ID": st.column_config.NumberColumn("ID", format="%d"),
            "Name": st.column_config.TextColumn("Name", width="medium", pinned=True),
            "Platform": st.column_config.TextColumn("Plattform", width="small"),
            "Abo $": st.column_config.NumberColumn("Abo $", format="%.0f"),
            "Abos": st.column_config.NumberColumn("Abonnenten", format="%.0f"),
            "Wochen": st.column_config.NumberColumn("Wochen", format="%.0f"),
            "Growth %": st.column_config.NumberColumn("Growth %", format="%.1f"),
            "Ertrag/Monat %": st.column_config.NumberColumn("Ertrag %/Mon.", format="%.1f"),
            "PF": st.column_config.NumberColumn("PF", format="%.2f"),
            "EQ-DD %": st.column_config.NumberColumn("EQ-DD %", format="%.1f"),
            "Bal-DD %": st.column_config.NumberColumn("Bal-DD %", format="%.1f"),
            "Trading-DD %": st.column_config.NumberColumn("Trading-DD %", format="%.1f"),
            "Winrate %": st.column_config.NumberColumn("Winrate %", format="%.1f"),
            "Verlustserie": st.column_config.NumberColumn("V-Serie", format="%d"),
            "Peak-Pos": st.column_config.NumberColumn("Peak-Pos", format="%d"),
            "Netto-Lots": st.column_config.NumberColumn("Netto-Lots", format="%.2f"),
            "Schock $": st.column_config.NumberColumn("Schock $", format="%.0f"),
            "Martingale": st.column_config.TextColumn("Marting.", width="small"),
            "Stop": st.column_config.TextColumn("Stop-Nachweis", width="medium"),
            "Score": st.column_config.ProgressColumn(
                "Risiko-Score ↓", min_value=1.0, max_value=10.0, format="%.1f",
                help="1–10: kleiner bedeutet weniger erkannte Risiken. Keine Ausfallwahrscheinlichkeit."),
            "Kurzfassung": st.column_config.TextColumn("Kurzfassung", width="large"),
            "Urteil": st.column_config.TextColumn("Urteil", width="medium"),
            "Fehler": st.column_config.TextColumn(None, width="small"),
            "Bericht": st.column_config.ButtonColumn(
                "Bericht", on_click=_open_report, key=f"{key}_bericht",
                type="primary"),
            "Link": st.column_config.LinkColumn("MQL5", width="small"),
        },
    )
    if event.selection.rows:
        return results[event.selection.rows[0]].id
    return None


def render_report_panel(results) -> None:
    """Ausfuehrlicher Gesamtbericht (per Bericht-Button in der Tabelle geoeffnet)."""
    report_id = st.session_state.get("report_signal_id")
    if report_id is None:
        return
    r = next((x for x in results if x.id == report_id), None)
    if r is None:
        st.session_state.pop("report_signal_id", None)
        return
    with st.container(border=True):
        head = st.container(horizontal=True)
        head.markdown(f"### :material/description: Ausführlicher Bericht — "
                      f"{r.name} (#{r.id})")
        with head:
            close_report = action_button("Schließen", key=f"close_report_{r.id}", help_key="reports")
        if close_report:
            st.session_state.pop("report_signal_id", None)
            st.rerun()
        if r.gesamtbericht:
            st.markdown(r.gesamtbericht)
        else:
            st.warning("Noch kein Gesamtbericht vorhanden. Erst den LLM-Lauf "
                       "(Schritt 4) starten — der Bericht wird vom konfigurierten Modell über "
                       "alle Teilergebnisse (Trades, Forensik, Risikoprofil) "
                       "geschrieben.")
        if r.llm_fehler:
            st.caption(f"LLM-Hinweis: {r.llm_fehler}")


def render_detail(result) -> None:
    """Detailansicht eines ScanResults: Kennzahlen, Teilergebnisse, Bericht."""
    st.subheader(f"{result.ampel} {result.name} · #{result.id}")
    if result.url:
        st.markdown(f"[Signal auf MQL5 öffnen]({result.url})")

    section_header("Risiko und Ertrag", "Historische Kennzahlen · fehlende Daten erscheinen als Strich.", help_key="risk_metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Risiko-Score", f"{result.score:.1f}" if result.score is not None else "—")
    col2.metric("Trading-DD (Engine)",
                f"{result.trading_dd_pct:.1f} %" if result.trading_dd_pct is not None else "—")
    col3.metric("EQ-DD (Plattform)",
                f"{result.dd_equity_pct:.1f} %" if result.dd_equity_pct is not None else "—")
    col4.metric("Ertrag/Monat",
                f"{result.ertrag_monat_pct:.1f} %" if result.ertrag_monat_pct is not None else "—")

    section_header("Positionierung und Belastung", help_key="exposure")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Winrate", f"{result.winrate_pct:.1f} %" if result.winrate_pct is not None else "—")
    col2.metric("Max. Verlustserie",
                f"{result.max_verlustserie}" if result.max_verlustserie is not None else "—",
                f"{result.verlustserie_usd:.0f} USD" if result.verlustserie_usd is not None else None)
    col3.metric("Peak-Positionen", f"{result.peak_positionen}" if result.peak_positionen is not None else "—")
    col4.metric("50-USD-Schock",
                f"{result.shock_usd:,.0f} USD".replace(",", ".") if result.shock_usd is not None else "—")

    st.markdown(f"**Urteil:** {result.urteil}")
    with st.container(border=True):
        section_header("Schutz und Stop-Nachweis", help_key="stop_evidence")
        st.markdown(result.stop_nachweis or "Kein Nachweis in den vorliegenden Daten.")
    if result.martingale_evidenz:
        st.markdown("**Martingale-Evidenz:** " + "; ".join(result.martingale_evidenz))
    if result.fehler:
        st.error(f"Fehler: {result.fehler}")

    section_header("Analysen und Bericht", "KI-Texte mit den berechneten Befunden abgleichen.", help_key="reports")
    with st.expander("1 · Trade-Analyse — Handelsweise aus den Trades",
                     icon=":material/query_stats:"):
        st.markdown(result.trade_analyse or "_Noch nicht erstellt (LLM-Lauf starten)._")
    with st.expander("2 · Risiko-Analyse — Forensik-Profil",
                     icon=":material/health_and_safety:"):
        st.markdown(result.risiko_analyse or "_Noch nicht erstellt (LLM-Lauf starten)._")
    with st.expander("3 · Ausführlicher Gesamtbericht",
                     icon=":material/description:", expanded=True):
        st.markdown(result.gesamtbericht or "_Noch nicht erstellt (LLM-Lauf starten)._")
    if result.llm_fehler:
        st.warning(f"LLM-Hinweis: {result.llm_fehler}")
