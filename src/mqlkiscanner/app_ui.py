# -*- coding: utf-8 -*-
"""Gemeinsame UI-Bausteine fuer die Streamlit-Seiten (Tabelle + Detail)."""
from __future__ import annotations

import html as _html
from copy import copy
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st
from mqlkiscanner import config
from mqlkiscanner import regelwerk
from mqlkiscanner.ampel_matrix import KRITERIEN, LABELS, kriterien_matrix
from mqlkiscanner.pdf_reports import (
    PdfRenderError,
    materialize_portfolio_pdf,
    persist_report_pdf,
    portfolio_pdf_spec,
    result_pdf_spec,
    result_snapshot_token,
)
from mqlkiscanner.ui_design import (action_button, section_header,
                                    urteile_farbig)

if TYPE_CHECKING:
    from mqlkiscanner.pipeline import ScanResult


def _result_identity(result) -> tuple:
    """Different local CSV snapshots can share one signal ID (including zero)."""
    return (result.source_kind, result.id, result.trades_path,
            result.trades_sha256, result.name)


def _result_snapshot_token(result) -> str:
    return result_snapshot_token(result)


def _display_path(path) -> str:
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


def render_result_pdf_viewer(
    result,
    kind: str,
    *,
    key: str,
    label: str | None = None,
    type: str = "secondary",
) -> None:
    """Persist one PDF and offer separate inline-view and save actions."""
    report, filename = result_pdf_spec(result, kind)
    path = None
    error = ""
    if report.body.strip():
        try:
            path = persist_report_pdf(report, snapshot=_result_snapshot_token(result))
        except (PdfRenderError, OSError) as exc:
            error = str(exc)
    visible_key = f"{key}_visible"
    visible = bool(st.session_state.get(visible_key))
    disabled = not bool(report.body.strip()) or bool(error)
    actions = st.container(horizontal=True, vertical_alignment="center")
    clicked = actions.button(
        "PDF schließen" if visible else
        (label or f"{report.kind.replace('_', ' ').title()} anzeigen"),
        key=key, type=type, icon=":material/picture_as_pdf:", disabled=disabled)
    actions.download_button(
        "PDF speichern",
        data=(lambda path=path: path.read_bytes()) if path is not None else b"",
        file_name=filename,
        mime="application/pdf",
        key=f"{key}_download",
        type="secondary",
        icon=":material/download:",
        disabled=disabled,
        on_click="ignore",
    )
    if clicked:
        visible = not visible
        st.session_state[visible_key] = visible
    if error:
        st.error(f"PDF konnte nicht bereitgestellt werden: {error}")
    elif visible and path is not None:
        st.pdf(path, height=820, key=f"{key}_document")
        st.caption(f"Automatisch gespeichert: `{_display_path(path)}`")


def render_portfolio_pdf_viewer(report: dict, *, key: str) -> None:
    """Persist and toggle the portfolio PDF inside the page."""
    pdf_report, filename = portfolio_pdf_spec(report)
    path = None
    error = ""
    if pdf_report.body.strip():
        try:
            path = materialize_portfolio_pdf(report)
        except (PdfRenderError, OSError) as exc:
            error = str(exc)
    visible_key = f"{key}_visible"
    visible = bool(st.session_state.get(visible_key))
    disabled = not bool(pdf_report.body.strip()) or bool(error)
    actions = st.container(horizontal=True, vertical_alignment="center")
    clicked = actions.button(
        "PDF schließen" if visible else "Portfolio-Gesamtbericht anzeigen",
        key=key, type="primary", icon=":material/picture_as_pdf:", disabled=disabled)
    actions.download_button(
        "PDF speichern",
        data=(lambda path=path: path.read_bytes()) if path is not None else b"",
        file_name=filename,
        mime="application/pdf",
        key=f"{key}_download",
        type="secondary",
        icon=":material/download:",
        disabled=disabled,
        on_click="ignore",
    )
    if clicked:
        visible = not visible
        st.session_state[visible_key] = visible
    if error:
        st.error(f"Portfolio-PDF konnte nicht bereitgestellt werden: {error}")
    elif visible and path is not None:
        st.pdf(path, height=820, key=f"{key}_document")
        st.caption(f"Automatisch gespeichert: `{_display_path(path)}`")


def clear_report_selection() -> None:
    st.session_state.pop("report_signal_id", None)
    st.session_state.pop("report_result_identity", None)


def results_to_dataframe(results, fresh_ids: set[int] | None = None) -> pd.DataFrame:
    results = tuple(copy(r) for r in results)
    rows = [r.to_row() for r in results]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if fresh_ids is not None:
        df.insert(0, "Stand", ["NEU" if r.id in fresh_ids else "" for r in results])
    df["Bericht vom"] = pd.to_datetime(df["Bericht vom"], errors="coerce")
    df["Bericht"] = ":material/picture_as_pdf: Öffnen"
    return df


def render_results_table(results, key: str = "results_table", compact: bool = True,
                         fresh_ids: set[int] | None = None) -> ScanResult | None:
    """Tabelle mit Ampel- und Bericht-Button; Rueckgabe = gewaehlter Ergebnissnapshot."""
    results = tuple(copy(r) for r in results)
    df = results_to_dataframe(results, fresh_ids=fresh_ids)
    if df.empty:
        st.info("Noch keine Ergebnisse — erst einen Scan starten oder die "
                "Verifikations-Datensaetze laden.")
        return None
    df["Link"] = [f"https://www.mql5.com/en/signals/{r.id}" if r.id else "" for r in results]

    def _open_report():
        click = st.session_state.get(f"{key}_bericht")  # ButtonColumn-Click-Info
        if click is not None and getattr(click, "row", None) is not None:
            st.session_state["report_signal_id"] = results[click.row].id
            st.session_state["report_result_identity"] = _result_identity(results[click.row])

    column_order = None
    if compact:
        column_order = (["Stand"] if fresh_ids is not None else []) + [
            "Ampel", "Name", "Stop", "Trading-DD %", "EQ-DD %", "Ertrag/Monat %",
            "Score", "Urteil", "Bericht vom", "Bericht", "Link"]

    event = st.dataframe(
        df,
        key=key,
        on_select="rerun",
        selection_mode="single-row",
        hide_index=True,
        height=560,
        column_order=column_order,
        column_config={
            "Stand": st.column_config.TextColumn(
                "Stand", width="small",
                help="NEU = im letzten Lauf dieser Sitzung aktualisiert"),
            "Ampel": st.column_config.TextColumn(
                "Status", width="small",
                help="Kandidat, Beobachtung, Risiko, Ausschluss oder Vorprüfung"),
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
            "Bericht vom": st.column_config.DatetimeColumn(
                "Bericht vom", width="medium", format="DD.MM.YYYY HH:mm",
                help="Erstellungszeitpunkt des angezeigten Gesamtberichts"),
            "Fehler": st.column_config.TextColumn(None, width="small"),
            "Bericht": st.column_config.ButtonColumn(
                "Bericht & PDF", on_click=_open_report, key=f"{key}_bericht",
                type="primary"),
            "Link": st.column_config.LinkColumn("MQL5", width="small"),
        },
    )
    if event.selection.rows:
        return results[event.selection.rows[0]]
    return None


def render_ampel_matrix(results, settings: dict | None = None) -> None:
    """Ampel-Matrix: Signal × Testkriterium mit Tooltips je Zelle.

    Kompakt genug fuer die Containerbreite (kein horizontales Scrollen):
    Kopfzeilen duerfen umbrechen, die Signalspalte ist mit Ellipse
    begrenzt (vollstaendiger Name steht im Tooltip). Spaltenkopf:
    Kriterium + ⓘ (title-Tooltip mit der Beschreibung). Zelle: Ampel-
    Emoji (title-Tooltip mit exakter Berechnung). Aller dynamische Text
    wird HTML-escaped — Signalnamen und Engine-Details duerfen beliebige
    Zeichen enthalten.
    """
    settings = settings if settings is not None else config.load_settings()
    esc = _html.escape
    rahmen = "border:1px solid rgba(128,128,128,0.35);padding:3px 6px;"
    zellen_style = rahmen + "text-align:center;"
    kopf = [f'<th style="{rahmen}text-align:left;width:11em;max-width:11em;">'
            f'Signal</th>']
    for kriterium in KRITERIEN:
        kopf.append(
            f'<th style="{rahmen}text-align:center;font-weight:600;" '
            f'title="{esc(kriterium.titel)}">'
            f'{esc(kriterium.titel)} '
            f'<span style="cursor:help;opacity:.7" '
            f'title="{esc(kriterium.beschreibung)}">&#9432;</span></th>')
    zeilen = []
    for result in results:
        matrix = kriterien_matrix(result, settings)
        name = result.name or f"#{result.id}"
        tooltip = f"{result.ampel} {name}"
        if result.urteil:
            tooltip += f" — {result.urteil}"
        zeile = [f'<th scope="row" style="{rahmen}text-align:left;'
                 f'max-width:11em;overflow:hidden;text-overflow:ellipsis;'
                 f'white-space:nowrap;" title="{esc(tooltip)}">'
                 f'{esc(result.ampel)} {esc(name)}</th>']
        for kriterium in KRITERIEN:
            zelle = matrix[kriterium.key]
            zell_tooltip = f"{zelle.ampel} {LABELS[zelle.ampel]} — {zelle.kurz}. " \
                           f"Berechnung: {zelle.detail}"
            zeile.append(f'<td style="{zellen_style}" '
                         f'title="{esc(zell_tooltip)}">{zelle.ampel}</td>')
        zeilen.append("<tr>" + "".join(zeile) + "</tr>")
    tabelle = ('<div style="overflow-x:auto"><table style="width:100%;'
               'border-collapse:collapse;font-size:.9em;table-layout:auto">'
               '<thead><tr>' + "".join(kopf) +
               "</tr></thead><tbody>" + "".join(zeilen) + "</tbody></table></div>")
    st.markdown(tabelle, unsafe_allow_html=True)
    st.caption("🟢 erfüllt · 🟡 Beobachtung/knapp · 🟠 Warnflag · 🔴 verletzt · "
               "⚪ keine Daten — Maus über ⓘ bzw. Ampel zeigt Bedeutung und "
               "exakte Berechnung. Die Matrix zeigt Einzelbedingungen, das "
               "Gesamturteil steht in der Spalte Ampel der anderen Ansichten.")


def render_report_panel(results) -> None:
    """Ausfuehrlicher Gesamtbericht (per Bericht-Button in der Tabelle geoeffnet)."""
    report_id = st.session_state.get("report_signal_id")
    if report_id is None:
        return
    identity = st.session_state.get("report_result_identity")
    matching = [x for x in results if (_result_identity(x) == identity if identity is not None
                                     else x.id == report_id)]
    # An old ID-only selection is safe only when it identifies exactly one row.
    r = matching[0] if len(matching) == 1 else None
    if r is None:
        clear_report_selection()
        return
    with st.container(border=True):
        head = st.container(horizontal=True)
        head.markdown(f"### :material/description: Ausführlicher Bericht — "
                      f"{r.name} (#{r.id})")
        with head:
            close_report = action_button("Schließen", key=f"close_report_{r.id}", help_key="reports")
        if close_report:
            clear_report_selection()
            st.rerun()
        render_result_pdf_viewer(
            r, "gesamtbericht", key=f"report_panel_final_{_result_snapshot_token(r)}",
            label="Gesamtbericht anzeigen", type="primary")
        st.caption("PDF ist bereits auf Platte gespeichert · kein neuer KI-Aufruf")
        if r.gesamtbericht:
            st.markdown(urteile_farbig(r.gesamtbericht), unsafe_allow_html=True)
        else:
            st.warning("Noch kein Gesamtbericht vorhanden. Erst den LLM-Lauf "
                       "(Schritt 4) starten — der Bericht wird vom konfigurierten Modell über "
                       "alle Teilergebnisse (Trades, Forensik, Risikoprofil) "
                       "geschrieben.")
        if r.llm_fehler:
            st.caption(f"LLM-Hinweis: {r.llm_fehler}")
        if r.pdf_fehler:
            st.error(r.pdf_fehler)
        if hint := getattr(r, "bericht_hinweis", ""):
            st.info(hint)
        st.markdown("**Zwischenanalysen öffnen**")
        render_result_pdf_viewer(
            r, "trade_analyse", key=f"report_panel_trade_{_result_snapshot_token(r)}",
            label="Trade-Analyse anzeigen")
        render_result_pdf_viewer(
            r, "risiko_analyse", key=f"report_panel_risk_{_result_snapshot_token(r)}",
            label="Risiko-Analyse anzeigen")


def render_detail(result) -> None:
    """Detailansicht eines ScanResults: Kennzahlen, Teilergebnisse, Bericht."""
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(f"{result.ampel} {result.name} · #{result.id}")
        if result.url:
            st.link_button("Auf MQL5 öffnen", result.url, icon=":material/open_in_new:")

    labels = {
        "🟢": ("Kandidat", "green"),
        "🟡": ("Beobachtung", "orange"),
        "🔴": ("Risiko-Flag", "red"),
        "⛔": ("Ausgeschlossen", "red"),
        "⚪": ("Vorprüfung", "gray"),
    }
    label, color = labels.get(result.ampel, ("Unklar", "gray"))
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(label, color=color)
            if result.trading_dd_pct is not None:
                st.badge(
                    "Drawdown-Grenze eingehalten"
                    if result.trading_dd_pct <= 30 else "Drawdown-Grenze überschritten",
                    color="green" if result.trading_dd_pct <= 30 else "red",
                )
            st.badge(
                "Ertragsziel erreicht"
                if result.ertrag_monat_pct is not None and result.ertrag_monat_pct > 5
                else "Ertragsziel nicht belegt",
                color="green"
                if result.ertrag_monat_pct is not None and result.ertrag_monat_pct > 5
                else "gray",
            )
        st.markdown("**Urteil**")
        st.write(result.urteil or "Noch kein belastbares Urteil vorhanden.")

    if result.ampel == "⛔":
        eintrag = regelwerk.ausgeschlossen_eintrag(result.id)
        grund = (eintrag or {}).get("grund", "")
        with st.container(border=True):
            section_header("Regelwerk · Ausschlussliste",
                           "Warum steht dieses Signal auf der Liste?",
                           help_key="ausschlussliste")
            if grund:
                st.markdown(f"**Gemessener Grund:** {_html.escape(grund)}")
            with st.expander("Vollständiges Regelwerk anzeigen",
                             expanded=False, icon=":material/gavel:"):
                st.markdown(regelwerk.regelwerk_markdown())

    with st.container(border=True):
        section_header("Schutz und Stop-Nachweis", "Kernfrage: bewiesen oder nur behauptet?",
                       help_key="stop_evidence")
        st.markdown(result.stop_nachweis or "Kein Nachweis in den vorliegenden Daten.")

    section_header("Risiko und Ertrag", "Historische Kennzahlen · fehlende Daten erscheinen als Strich.", help_key="risk_metrics")
    with st.container(horizontal=True):
        st.metric("Risiko-Score", f"{result.score:.1f}" if result.score is not None else "—",
                  border=True)
        st.metric("Trading-DD max.",
                  f"{result.trading_dd_pct:.1f} %" if result.trading_dd_pct is not None else "—",
                  border=True)
        st.metric("EQ-DD (Plattform)",
                  f"{result.dd_equity_pct:.1f} %" if result.dd_equity_pct is not None else "—",
                  border=True)
        st.metric("Ertrag / Monat",
                  f"{result.ertrag_monat_pct:.1f} %" if result.ertrag_monat_pct is not None else "—",
                  border=True)

    section_header("Positionierung und Belastung", help_key="exposure")
    with st.container(horizontal=True):
        st.metric("Winrate", f"{result.winrate_pct:.1f} %" if result.winrate_pct is not None else "—",
                  border=True)
        st.metric("Max. Verlustserie",
                  f"{result.max_verlustserie}" if result.max_verlustserie is not None else "—",
                  f"{result.verlustserie_usd:.0f} USD" if result.verlustserie_usd is not None else None,
                  border=True)
        st.metric("Peak-Positionen",
                  f"{result.peak_positionen}" if result.peak_positionen is not None else "—",
                  border=True)
        st.metric("50-USD-Schock",
                  f"{result.shock_usd:,.0f} USD".replace(",", ".")
                  if result.shock_usd is not None else "—",
                  border=True)
    if result.martingale_evidenz:
        st.markdown("**Martingale-Evidenz:** " + "; ".join(result.martingale_evidenz))
    if result.fehler:
        st.error(f"Fehler: {result.fehler}")

    section_header("Analysen und Bericht", "KI-Texte mit den berechneten Befunden abgleichen.", help_key="reports")
    with st.expander("1 · Trade-Analyse — Handelsweise aus den Trades",
                     icon=":material/query_stats:"):
        render_result_pdf_viewer(
            result, "trade_analyse", key=f"detail_trade_{_result_snapshot_token(result)}",
            label="PDF anzeigen")
        st.markdown(result.trade_analyse or "_Noch nicht erstellt (LLM-Lauf starten)._")
    with st.expander("2 · Risiko-Analyse — Forensik-Profil",
                     icon=":material/health_and_safety:"):
        render_result_pdf_viewer(
            result, "risiko_analyse", key=f"detail_risk_{_result_snapshot_token(result)}",
            label="PDF anzeigen")
        st.markdown(result.risiko_analyse or "_Noch nicht erstellt (LLM-Lauf starten)._")
    with st.expander("3 · Ausführlicher Gesamtbericht",
                     icon=":material/description:", expanded=True):
        render_result_pdf_viewer(
            result, "gesamtbericht", key=f"detail_final_{_result_snapshot_token(result)}",
            label="PDF anzeigen", type="primary")
        if result.gesamtbericht:
            st.markdown(urteile_farbig(result.gesamtbericht), unsafe_allow_html=True)
        else:
            st.markdown("_Noch nicht erstellt (LLM-Lauf starten)._")
    if result.llm_fehler:
        st.warning(f"LLM-Hinweis: {result.llm_fehler}")
    if result.pdf_fehler:
        st.error(result.pdf_fehler)
    if hint := getattr(result, "bericht_hinweis", ""):
        st.info(hint)
