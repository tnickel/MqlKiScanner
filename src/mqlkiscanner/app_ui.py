# -*- coding: utf-8 -*-
"""Gemeinsame UI-Bausteine fuer die Streamlit-Seiten (Tabelle + Detail)."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def results_to_dataframe(results) -> pd.DataFrame:
    rows = [r.to_row() for r in results]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df


def render_results_table(results, key: str = "results_table") -> int | None:
    """Tabelle mit Ampel-Spalte; Rueckgabe = gewaehlte Signal-ID (oder None)."""
    df = results_to_dataframe(results)
    if df.empty:
        st.info("Noch keine Ergebnisse — erst einen Scan starten oder die "
                "Verifikations-Datensaetze laden.")
        return None
    df["Link"] = [f"https://www.mql5.com/en/signals/{r.id}" if r.id else "" for r in results]

    event = st.dataframe(
        df,
        key=key,
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
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
                "Risiko-Score", min_value=1.0, max_value=10.0, format="%.1f"),
            "Urteil": st.column_config.TextColumn("Urteil", width="large"),
            "Fehler": st.column_config.TextColumn(None, width="small"),
            "Link": st.column_config.LinkColumn("MQL5", width="small"),
        },
    )
    if event.selection.rows:
        return results[event.selection.rows[0]].id
    return None


def render_detail(result) -> None:
    """Detailansicht eines ScanResults: Forensik-Karten + LLM-Texte."""
    st.subheader(f"{result.ampel} {result.name} #{result.id}", divider=True)
    if result.url:
        st.markdown(f"[Signal auf MQL5 öffnen]({result.url})")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Risiko-Score", f"{result.score:.1f}" if result.score is not None else "—")
    col2.metric("Trading-DD (Engine)",
                f"{result.trading_dd_pct:.1f} %" if result.trading_dd_pct is not None else "—")
    col3.metric("EQ-DD (Plattform)",
                f"{result.dd_equity_pct:.1f} %" if result.dd_equity_pct is not None else "—")
    col4.metric("Ertrag/Monat",
                f"{result.ertrag_monat_pct:.1f} %" if result.ertrag_monat_pct is not None else "—")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Winrate", f"{result.winrate_pct:.1f} %" if result.winrate_pct is not None else "—")
    col2.metric("Max. Verlustserie",
                f"{result.max_verlustserie}" if result.max_verlustserie is not None else "—",
                f"{result.verlustserie_usd:.0f} USD" if result.verlustserie_usd is not None else None)
    col3.metric("Peak-Positionen", f"{result.peak_positionen}" if result.peak_positionen is not None else "—")
    col4.metric("50-USD-Schock",
                f"{result.shock_usd:,.0f} USD".replace(",", ".") if result.shock_usd is not None else "—")

    st.markdown(f"**Urteil:** {result.urteil}")
    st.markdown(f"**Stop-Nachweis:** {result.stop_nachweis or '—'}")
    if result.martingale_evidenz:
        st.markdown("**Martingale-Evidenz:** " + "; ".join(result.martingale_evidenz))
    if result.fehler:
        st.error(f"Fehler: {result.fehler}")

    with st.expander("Stufe-1-Profil (GLM Flash)", icon=":material/psychology:"):
        st.markdown(result.stufe1_profil or "_Noch nicht erstellt (LLM-Lauf starten)._")
    with st.expander("Stufe-2-Verdict (GLM stark)", icon=":material/gavel:"):
        st.markdown(result.stufe2_verdict or "_Noch nicht erstellt (Finalist + LLM-Lauf noetig)._")
    if result.llm_fehler:
        st.warning(f"LLM-Hinweis: {result.llm_fehler}")
