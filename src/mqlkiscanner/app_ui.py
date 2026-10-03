# -*- coding: utf-8 -*-
"""Gemeinsame UI-Bausteine fuer die Streamlit-Seiten (Tabelle + Detail)."""
from __future__ import annotations

import html as _html
import math
import re
from copy import copy
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st
from mqlkiscanner import config, db, downloader_client, downloader_sync, fix_signale, llm_runner
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
from mqlkiscanner.ui_design import (aktivitaets_banner, action_button,
                                    section_header, urteile_farbig)

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


# Laengen-Markierung: Dokumente ab dieser Groesse gelten als "lang" und ihre
# Anzeige-Buttons werden gelb gefaerbt — kurze und lange Dokumente sind so auf
# einen Blick unterscheidbar (Nutzer-Wunsch; die Tiefenanalyse ist typischer-
# weise lang). Zeichen fuer Bericht-Texte, kB fuer Downloader-PDF-Groessen.
_LANG_ZEICHEN = 8000
_LANG_KB = 100


def _gelbe_anzeige(key: str, lang: bool) -> None:
    """Faerbt den Button mit dem Widget-Key gelb, wenn das Dokument lang ist.

    Der Selektor muss das Theme uebertreffen, das sekundaere/primare Buttons
    mit !important und Spezifitaet (0,2,1) faerbt — daher die Kette ueber
    .stApp .stElementContainer (0,3,1).
    """
    if not lang:
        return
    safe = re.sub(r"[^A-Za-z0-9_-]", "", key)
    st.markdown(
        f"<style>.stApp .stElementContainer.st-key-{safe} button{{"
        f"background:rgba(255,193,7,.16)!important;"
        f"color:#ffd76a!important;border:1px solid rgba(255,193,7,.6)!important;}}"
        f"</style>",
        unsafe_allow_html=True,
    )


def dokumente_zelle(normale: int, tiefenanalysen: int, downloader: int = 0) -> str:
    """Tabellenzelle 'Dokumente': 📄 = normale Berichte + Downloader-PDFs,
    🟡 = Erweiterte KI-Analysen (Tiefenanalysen) — auf einen Blick getrennt."""
    teile = []
    if normale + downloader:
        teile.append(f"📄 {normale + downloader}")
    if tiefenanalysen:
        teile.append(f"🟡 {tiefenanalysen}")
    return " · ".join(teile)


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
    lang = len(report.body) >= _LANG_ZEICHEN
    _gelbe_anzeige(key, lang)
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
        key=key, type=type, icon=":material/picture_as_pdf:", disabled=disabled,
        help="Langes Dokument — gelb markiert." if lang else None)
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


def render_portfolio_pdf_viewer(report: dict, *, key: str,
                                ergebnisse=None) -> None:
    """Persist and toggle the portfolio PDF inside the page.

    ergebnisse: aktuelle 🟢-Ergebnisse — erzeugt den Detail-Anhang der
    empfohlenen Strategien (Nutzer-Wunsch 30.09.2026). Aufrufer ohne
    Ergebnisse bekommen das klassische Nur-Text-PDF.
    """
    pdf_report, filename = portfolio_pdf_spec(report, ergebnisse=ergebnisse)
    path = None
    error = ""
    if pdf_report.body.strip():
        try:
            path = materialize_portfolio_pdf(report, ergebnisse=ergebnisse)
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


_ABO_FENSTER = {"gesamt": "Gesamtverlauf", "30": "letzte 30 Tage",
                "7": "letzte 7 Tage"}


def _abo_delta_zelle(wert: int | None) -> str:
    """Tabellenzelle für 7-/30-Tage-Bilanz: + grün, − rot, 0 neutral."""
    if wert is None:
        return ""
    if wert > 0:
        return f"🟢 +{wert}"
    if wert < 0:
        return f"🔴 {wert}"
    return f"⚪ {wert}"


# Regex für die Exposure-Fehlermeldung „Unbekannte Instrumente ohne
# belegte Kontraktgroesse: X, Y" — ganze Forensik gescheitert (kein
# Forensik-JSON mit symbole_ohne_kontrakt, weil analyze vor dem Schreiben
# abbrach). Die Arbeitsliste soll diese Fälle trotzdem zeigen.
_KONTRAKT_FEHLER_RE = re.compile(
    r"Unbekannte Instrumente ohne belegte Kontraktgroesse:\s*"
    r"([A-Za-z0-9._+-]+(?:,\s*[A-Za-z0-9._+-]+)*)")


def fehlende_kursdaten_arbeitsliste(results) -> list[dict]:
    """Aggregierte Arbeitsliste fehlender Kurs-/Kontraktsbasis (Nutzer-
    Wunsch 03.10.: „sollte im Bericht erscheinen, damit ich weiß, wo ich
    dran arbeiten kann"). Rückgabe je Symbol: {symbol, grund, signale}."""
    eintraege: dict[tuple[str, str]] = {}
    for r in results:
        for symbol in (getattr(r, "equity_rekon_ohne_kurse", None) or []):
            eintraege.setdefault((str(symbol), "kein Kurs im MT5-Referenzterminal"),
                                 []).append(getattr(r, "name", "") or f"#{r.id}")
        for symbol in (getattr(r, "equity_rekon_ohne_kontrakt", None) or []):
            eintraege.setdefault((str(symbol), "Kontraktgröße nicht belegt (contract_specs.json)"),
                                 []).append(getattr(r, "name", "") or f"#{r.id}")
        # Ganze Forensik am Kontrakt gescheitert (Fehler-Feld parsen).
        treffer = _KONTRAKT_FEHLER_RE.search(getattr(r, "fehler", "") or "")
        if treffer:
            for symbol in [s.strip() for s in treffer.group(1).split(",") if s.strip()]:
                eintraege.setdefault((symbol, "Kontraktgröße nicht belegt (contract_specs.json)"),
                                     []).append(getattr(r, "name", "") or f"#{r.id}")
    return [{"symbol": sym, "grund": grund, "signale": sorted(set(namen))}
            for (sym, grund), namen in sorted(eintraege.items())]


def render_fehlende_kursdaten(results) -> None:
    """Arbeitsliste: welche Symbole fehlen bei welchen Signalen."""
    eintraege = fehlende_kursdaten_arbeitsliste(results)
    if not eintraege:
        return
    with st.container(border=True):
        st.markdown(f":material/warning: **Fehlende Kursdaten · Arbeitsliste** — "
                    f"{len(eintraege)} Symbole schränken die Equity-Nachmessung ein "
                    "(gemessener Max-Drawdown kann zu niedrig sein). "
                    "Beheben und dann neu scannen:")
        for e in eintraege[:12]:
            namen = ", ".join(e["signale"][:4]) + (" …" if len(e["signale"]) > 4 else "")
            st.markdown(f"• **{e['symbol']}** — {e['grund']} · {len(e['signale'])} "
                        f"Signal(e): {namen}")
        if len(eintraege) > 12:
            st.caption(f"… und {len(eintraege) - 12} weitere.")


@st.dialog("Abonnenten-Verlauf", width="large")
def _abo_verlauf_dialog(signal_id: int, name: str, fenster: str) -> None:
    """Fenster mit dem gespiegelten Abonnenten-Verlauf (Gesamt / 30 / 7 Tage)."""
    punkte = db.get_history(signal_id)
    titel = _ABO_FENSTER.get(fenster, fenster)
    st.caption(f"{name} (#{signal_id}) · {titel} · Quelle: MqlDownloader-Spiegel")
    if not punkte:
        st.info("Kein Verlauf gespeichert. Erst den MqlDownloader-Abgleich "
                "ausführen (Station 6 oder Button auf dieser Seite).")
        return
    df = pd.DataFrame(punkte)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts")
    if fenster in ("30", "7"):
        grenze = pd.Timestamp.now() - pd.Timedelta(days=int(fenster))
        df = df[df["ts"] >= grenze]
        if df.empty:
            st.info(f"Keine Messpunkte in den letzten {fenster} Tagen — "
                    "der Downloader sammelt hier erst noch.")
            return
    pivot = df.pivot_table(index="ts", columns="version",
                           values="subscribers", aggfunc="last").sort_index()
    st.line_chart(pivot, height=280)
    with st.container(horizontal=True):
        for version, gruppe in df.groupby("version"):
            reihe = gruppe.sort_values("ts")
            erster, letzter = reihe.iloc[0], reihe.iloc[-1]
            if pd.isna(erster["subscribers"]) or pd.isna(letzter["subscribers"]):
                delta_text, aktuell_text = "—", "—"
            else:
                delta = int(letzter["subscribers"]) - int(erster["subscribers"])
                delta_text = f"{'+' if delta > 0 else ''}{delta} im Fenster"
                aktuell_text = str(int(letzter["subscribers"]))
            st.metric(f"{version} · aktuell", aktuell_text,
                      delta_text, delta_color="off", border=True)
    st.caption("Bilanz im Fenster = neuester Messpunkt gegen den ersten "
               "Messpunkt des Fensters. Der Verlauf ist Marktbeobachtung "
               "und ändert keine Bewertung.")


def _max_drawdown_farbe(value, limit) -> str:
    """Farbstatus der gemessenen Equity; fehlende Werte bleiben grau."""
    try:
        value, limit = float(value), float(limit)
    except (TypeError, ValueError):
        return "gray"
    if not math.isfinite(value) or value < 0 or not math.isfinite(limit) or limit <= 0:
        return "gray"
    if value <= 0.8 * limit:
        return "green"
    return "orange" if value <= limit else "red"


def _max_drawdown_zellenstil(value, limit) -> str:
    """Dezente Hinterlegung im dunklen Theme: schwache Fläche + farbiger
    Text, KEIN pastellfarbener Block mit fetter Schrift (Nutzer 03.10.).
    Fehlende Messung bleibt ganz unmarkiert (kein grauer Klotz)."""
    akzente = {
        "green": ("rgba(34,197,94,0.10)", "#4ade80"),
        "orange": ("rgba(249,115,22,0.12)", "#fb923c"),
        "red": ("rgba(239,68,68,0.16)", "#f87171"),
        "gray": ("transparent", ""),
    }
    hintergrund, text = akzente[_max_drawdown_farbe(value, limit)]
    if not text:
        return ""
    return f"background-color: {hintergrund}; color: {text}"


def results_to_dataframe(results, fresh_ids: set[int] | None = None,
                         fix_ids: set[int] | None = None) -> pd.DataFrame:
    results = tuple(copy(r) for r in results)
    rows = [r.to_row() for r in results]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if fresh_ids is not None:
        df.insert(0, "Stand", ["NEU" if r.id in fresh_ids else "" for r in results])
    if fix_ids is not None:
        df.insert(0 if fresh_ids is None else 1, "Fix",
                  ["📌 FIX" if r.id in fix_ids else "" for r in results])
    df["Bericht vom"] = pd.to_datetime(df["Bericht vom"], errors="coerce")
    df["Bericht"] = ":material/picture_as_pdf: Öffnen"
    return df


def render_results_table(results, key: str = "results_table", compact: bool = True,
                         fresh_ids: set[int] | None = None,
                         fix_ids: set[int] | None = None) -> ScanResult | None:
    """Tabelle mit Ampel- und Bericht-Button; Rueckgabe = gewaehlter Ergebnissnapshot."""
    results = tuple(copy(r) for r in results)
    df = results_to_dataframe(results, fresh_ids=fresh_ids, fix_ids=fix_ids)
    if df.empty:
        st.info("Noch keine Ergebnisse — erst einen Scan starten oder die "
                "Verifikations-Datensaetze laden.")
        return None
    df["Link"] = [f"https://www.mql5.com/en/signals/{r.id}" if r.id else "" for r in results]
    docs_counts = db.downloader_report_counts([r.id for r in results])
    abo = downloader_sync.abo_bilanz(
        [r.id for r in results],
        platformen={r.id: getattr(r, "platform", "") or "" for r in results})
    df["Abonnenten"] = [(str(abo[r.id]["abonnenten"])
                         if abo[r.id]["abonnenten"] is not None else "")
                        for r in results]
    df["30 Tage"] = [_abo_delta_zelle(abo[r.id]["tage30"]) for r in results]
    df["7 Tage"] = [_abo_delta_zelle(abo[r.id]["tage7"]) for r in results]

    df["Dokumente"] = [
        dokumente_zelle(
            normale=sum(bool(getattr(r, feld, "")) for feld in
                        ("trade_analyse", "risiko_analyse", "gesamtbericht")),
            tiefenanalysen=1 if getattr(r, "tiefenanalyse", "") else 0,
            downloader=docs_counts.get(r.id, 0),
        )
        for r in results
    ]

    def _open_report():
        click = st.session_state.get(f"{key}_bericht")  # ButtonColumn-Click-Info
        if click is not None and getattr(click, "row", None) is not None:
            st.session_state["report_signal_id"] = results[click.row].id
            st.session_state["report_result_identity"] = _result_identity(results[click.row])

    def _open_docs():
        click = st.session_state.get(f"{key}_docs")  # ButtonColumn-Click-Info
        if click is not None and getattr(click, "row", None) is not None:
            st.session_state["downloader_doc_signal_id"] = results[click.row].id
            st.session_state["downloader_doc_identity"] = _result_identity(results[click.row])

    def _open_abo(fenster: str):
        def handler():
            click = st.session_state.get(f"{key}_abo_{fenster}")
            if click is not None and getattr(click, "row", None) is not None:
                treffer = results[click.row]
                _abo_verlauf_dialog(treffer.id, treffer.name or f"#{treffer.id}",
                                    fenster)
        return handler

    def _open_eqdd():
        # Equity-DD-Studie (Nutzer-Wunsch 03.10.2026): On-Demand-Nachmessung
        # aus Kursen je Signal — Dialog mit Kurve, offiziellem Betrag und
        # offener Position. Lazy import: das UI-Modul zieht Kursdaten/Plotly,
        # das hier nur bei tatsächlichem Klick geladen werden soll.
        click = st.session_state.get(f"{key}_eqdd")
        if click is not None and getattr(click, "row", None) is not None:
            from .equity_studie_ui import equity_studie_dialog
            equity_studie_dialog(results[click.row])

    df["Studie"] = ["Studie"] * len(results)

    column_order = None
    if compact:
        # Die DREI Drawdown-Werte direkt nebeneinander (Nutzer 03.10.: „dann
        # sieht man das sofort") — gemessene Equity, geschlossene Trades,
        # Plattform-Selbstauskunft; der Studie-Button folgt sofort. Die
        # breite Textspalte Equity-Messung bleibt in der Ansicht
        # „Alle Kennzahlen" und bremst die Kompaktansicht nicht.
        column_order = ((["Stand"] if fresh_ids is not None else [])
                        + (["Fix"] if fix_ids is not None else [])
                        + ["Ampel", "Name", "Quelle", "Stop", "Max-Drawdown %",
                           "Trading-DD % (geschlossen)", "Drawdown % (Plattform)",
                           "Studie",
                           "Gewinn %/Monat", "RetDD", "Ertrag/Monat %", "Score",
                           "Urteil", "Bericht vom", "Bericht",
                           "Link", "Abonnenten", "30 Tage", "7 Tage", "Dokumente"])

    limit = config.load_settings().get("schranke_eq_dd_pct", 30.0)
    # Styler färbt nur Zellen. Zahlenformate, ButtonColumns und Auswahl
    # bleiben bei der nativen Dataframe-Konfiguration.
    styled = df.style.map(lambda value: _max_drawdown_zellenstil(value, limit),
                          subset=["Max-Drawdown %"])
    event = st.dataframe(
        styled,
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
            "Fix": st.column_config.TextColumn(
                "Fix", width="small",
                help="📌 FIX = diese Signal-ID steht auf der Immer-Scannen-Liste: "
                     "Jeder Scan prüft sie — auch wenn sie aus den MQL5-Top-Listen "
                     "rutscht oder den Vorfiltern nicht genügt. Setzen/entfernen "
                     "per Checkmark im Detail oder auf der Ergebnisseite unter "
                     "„Fix-IDs · immer scannen“."),
            "Ampel": st.column_config.TextColumn(
                "Status", width="small",
                help="Kandidat, Beobachtung, Risiko, Ausschluss oder Vorprüfung"),
            "ID": st.column_config.NumberColumn("ID", format="%d"),
            "Name": st.column_config.TextColumn("Name", width="medium", pinned=True),
            "Platform": st.column_config.TextColumn("Plattform", width="small"),
            "Quelle": st.column_config.TextColumn(
                "Quelle", width="small",
                help="Datenquelle des Signals — Kürzel aus Admin → Datenquellen (doc/20)"),
            "Abo $": st.column_config.NumberColumn("Abo $", format="%.0f"),
            "Abos": st.column_config.NumberColumn("Abonnenten", format="%.0f"),
            "Wochen": st.column_config.NumberColumn("Wochen", format="%.0f"),
            "Growth %": st.column_config.NumberColumn("Growth %", format="%.1f"),
            "Ertrag/Monat %": st.column_config.NumberColumn("Ertrag %/Mon.", format="%.1f"),
            "Gewinn %/Monat": st.column_config.NumberColumn(
                "Gewinn %/Monat", format="%.2f%%",
                help="Eigene geometrische Monatsrendite aus den Trade-Daten. "
                     "Fehlt die Berechnung, bleibt das Feld leer; "
                     "Plattform-Ertrag wird nicht als Ersatz verwendet."),
            "RetDD": st.column_config.NumberColumn(
                "RetDD", format="%.2f",
                help="Gewinn %/Monat ÷ gemessener Max-Drawdown % (Equity). "
                     "Dimensionsloses Verhältnis; höher bedeutet mehr "
                     "historischen Monatsgewinn je Drawdown-Punkt. "
                     "Ohne Gewinn oder belastbare Equity-Messung sowie "
                     "bei Max-Drawdown 0 bleibt RetDD leer. "
                     "Trading-DD und Plattform-DD ersetzen diese Messung nicht."),
            "PF": st.column_config.NumberColumn("PF", format="%.2f"),
            "Drawdown % (Plattform)": st.column_config.NumberColumn(
                "Drawdown % (Plattform)", format="%.1f",
                help="Plattform-Selbstauskunft „By Equity“ — vom Broker "
                     "gemeldet, keine eigene Messung."),
            "Balance-DD % (Plattform)": st.column_config.NumberColumn(
                "Balance-DD % (Plattform)", format="%.1f",
                help="Plattform-Selbstauskunft „By Balance“ — kann bei "
                     "Auszahlungen deutlich höher ausfallen als der "
                     "Trading-DD aus geschlossenen Trades."),
            "Max-Drawdown %": st.column_config.NumberColumn(
                "Max-Drawdown % (Equity)", format="%.1f",
                help="Gemessene Equity inklusive offener Gewinne und Verluste: "
                     "höchster belastbarer Wert aus Kurs-Nachmessung oder Monitor. "
                     "Die Kurs-Nachmessung misst virtuelle Trading-Equity "
                     "ohne spätere Ein-/Auszahlungen; der Monitor hat eine eigene Basis. "
                     "Fehlt die Messung, bleibt das Feld leer. H1-Kurse erfassen "
                     "keine Tiefs innerhalb einer Stunde. Farbe: grün bis 80 % "
                     "der konfigurierten Drawdown-Grenze, gelb bis zur Grenze, "
                     "rot darüber, grau bei fehlender Messung."),
            "Trading-DD % (geschlossen)": st.column_config.NumberColumn(
                "Trading-DD % (geschlossen)", format="%.1f",
                help="Drawdown aus den Nettogewinnen geschlossener Trades. "
                     "Zwischenzeitliche Verluste offener Positionen fehlen hier."),
            "Equity-Messung": st.column_config.TextColumn(
                "Equity-Messung", width="medium",
                help="Messquelle oder Grund, warum keine belastbare "
                     "Equity-Nachmessung vorhanden ist."),
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
            "Studie": st.column_config.ButtonColumn(
                "Studie", width="small",
                help="Klick: Max-Drawdown aus echten Kursen nachmessen — "
                     "stundenfeine Kurve mit realisiertem Betrag UND offenem "
                     "Betrag (floating), GMT-Abgleich je Währungspaar. "
                     "Öffnet ein Fenster mit Chart, Zoom und Risiko-Texten; "
                     "dauert einige Sekunden (MT5-Terminal + Kurse laden).",
                on_click=_open_eqdd, key=f"{key}_eqdd"),
            "Link": st.column_config.LinkColumn("MQL5", width="small"),
            "Abonnenten": st.column_config.ButtonColumn(
                "Abonnenten",
                help="Klick: Gesamtverlauf der Abonnenten anzeigen (MqlDownloader)",
                on_click=_open_abo("gesamt"), key=f"{key}_abo_gesamt"),
            "30 Tage": st.column_config.ButtonColumn(
                "30 Tage",
                help="Klick: Verlauf der letzten 30 Tage anzeigen",
                on_click=_open_abo("30"), key=f"{key}_abo_30"),
            "7 Tage": st.column_config.ButtonColumn(
                "7 Tage",
                help="Klick: Verlauf der letzten 7 Tage anzeigen",
                on_click=_open_abo("7"), key=f"{key}_abo_7"),
            "Dokumente": st.column_config.ButtonColumn(
                "Dokumente",
                help="📄 Berichte + Testreports aus dem MqlDownloader · "
                     "🟡 Erweiterte KI-Analysen (Tiefenanalysen). "
                     "Klick: alle PDFs des Signals öffnen.",
                on_click=_open_docs, key=f"{key}_docs"),
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


_RICHTUNG_LABEL = {"verbesserung": ("📈", "Verbesserung", st.success),
                   "verschlechterung": ("📉", "Verschlechterung", st.error),
                   "hinweis": ("ℹ️", "Einordnung", st.warning)}


def render_wechsel_karten(wechsel: list[dict]) -> None:
    """Wechsel-Protokoll als einzelne, deutlich sichtbare Karten rendern.

    Je Karte: Farbwechsel (groß) bzw. gekipptes Kriterium, Signal, Zeitpunkt,
    Laufart und je Kriterium alt → neu mit Kurzzustand und exakter
    Berechnung (Nachvollziehbarkeit). Verschlechterungen rot, Verbesserungen
    grün, reine Einordnungen/Kriteriumskippen gelb — so bleibt die Liste
    auch ohne Lesen der Details erfassbar. Nicht horizontales Scrollen:
    eine Karte je Ereignis, Text bricht um.
    """
    if not wechsel:
        st.info("Noch kein Wechsel protokolliert. Die Chronik beginnt mit dem "
                "nächsten Scan; jeder weitere Scan wird gegen den Vorgänger "
                "verglichen.", icon=":material/history:")
        return
    quelle_label = {"full": "Full-Scan", "gelbgruen": "Teilscan"}
    from .agenten import dossier as dossier_db
    _stilbruch_cache: dict[int, list[dict]] = {}
    for w in wechsel:
        icon, label, karte = _RICHTUNG_LABEL.get(w.get("richtung", "hinweis"),
                                                 _RICHTUNG_LABEL["hinweis"])
        name = w.get("name") or f"#{w.get('signal_id')}"
        pfeil = (f"{w.get('ampel_alt') or '—'} → {w.get('ampel_neu')}"
                 if w.get("farbwechsel") else
                 f"{w.get('ampel_neu')} (Farbe unverändert, Kriterium gekippt)")
        score_text = ""
        if w.get("score_alt") is not None and w.get("score_neu") is not None:
            score_text = f" · Score {w['score_alt']:g} → {w['score_neu']:g}"
        zeiten = (f"{w.get('ts') or ''} · "
                  f"{quelle_label.get(w.get('quelle'), w.get('quelle') or '—')}")
        body = [f"{icon} **{pfeil} · {name}** · #{w.get('signal_id')}"
                f"{score_text} · {label}", f"*{zeiten}*"]
        # Stilbruch-Vergangenheit mitliefern (Nutzer-Wunsch): ein Wechsel auf
        # 🟢 soll nicht überdecken, dass der Betreuer früher einen Stilbruch
        # festgestellt hat — ein Lookup je Signal, gecacht für die Liste.
        sig = w.get("signal_id")
        if sig is not None and sig not in _stilbruch_cache:
            _stilbruch_cache[sig] = dossier_db.stilbruch_historie(int(sig),
                                                                  limit=1)
        hist = _stilbruch_cache.get(sig) or []
        if hist:
            body.append(f"⚠️ **Stilbruch-Historie** (zuletzt "
                        f"{str(hist[0]['ts'])[:10]}) — die Vergangenheit bleibt "
                        f"im Dossier ablesbar, unabhängig vom heutigen "
                        f"Ampel-Urteil.")
        gruende = w.get("gruende") or []
        if gruende:
            body.append("**Geänderte Kriterien:**")
            for g in gruende:
                body.append(f"- {g.get('ampel_alt')} → {g.get('ampel_neu')} "
                            f"**{g.get('titel')}**: {g.get('kurz_alt')} → "
                            f"{g.get('kurz_neu')}")
                if g.get("detail"):
                    body.append(f"  - *{g['detail']}*")
        elif w.get("urteil_neu"):
            body.append(f"Neues Urteil: *{w['urteil_neu']}*")
        karte("\n".join(body))


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
        st.markdown("**Erweiterte KI-Analyse (Tiefenanalyse)**")
        if r.tiefenanalyse:
            render_result_pdf_viewer(
                r, "tiefenanalyse",
                key=f"report_panel_tiefe_{_result_snapshot_token(r)}",
                label="Tiefenanalyse anzeigen")
            with st.expander("Text der Tiefenanalyse", icon=":material/notes:"):
                st.markdown(urteile_farbig(r.tiefenanalyse), unsafe_allow_html=True)
        else:
            st.caption("In dieser Quelle keine Tiefenanalyse enthalten. Sitzung "
                       "und Archiv sind Momentaufnahmen und nehmen später "
                       "erstellte Analysen nicht auf — wechsle oben zur Quelle "
                       "„Datenbank (alle Berichte)“, oder starte sie per "
                       "„Erweiterte KI Analyse machen“ in der Detailansicht.")


def _downloader_versions(result) -> list[str]:
    """API-Versionen, die für das Signal gefragt werden (Plattform oder beide)."""
    return downloader_sync.versions(getattr(result, "platform", ""))


def _dl_fetch_history(result) -> int:
    """Abonnenten-Verlauf holen und spiegeln (Logik: downloader_sync)."""
    return downloader_sync.sync_history(result.id, getattr(result, "platform", ""))


def _dl_fetch_reports(result) -> list[str]:
    """Testreport-PDFs spiegeln, unveränderte überspringen (downloader_sync)."""
    return downloader_sync.sync_reports(result.id, getattr(result, "platform", ""))


def _render_dl_history(result) -> None:
    """Gespeicherten Abonnenten-Verlauf als Chart, Kennzahl und Tabelle."""
    punkte = db.get_history(result.id)
    if not punkte:
        st.info("Noch kein Abonnenten-Verlauf gespeichert. "
                "„Nutzer-Verlauf aktualisieren“ lädt ihn aus dem MqlDownloader.")
        return
    df = pd.DataFrame(punkte)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts")
    pivot = df.pivot_table(index="ts", columns="version",
                           values="subscribers", aggfunc="last").sort_index()
    st.line_chart(pivot, height=240)
    with st.container(horizontal=True):
        for version, gruppe in df.groupby("version"):
            latest = gruppe.iloc[-1]
            stand = latest["ts"].strftime("%d.%m.%Y %H:%M")
            wert = ("—" if pd.isna(latest["subscribers"])
                    else f"{int(latest['subscribers'])}")
            st.metric(f"Abonnenten ({version})", wert,
                      f"Stand {stand}", delta_color="off", border=True)
    with st.expander("Datenpunkte anzeigen", icon=":material/table_rows:"):
        tabelle = df[["version", "ts", "subscribers", "change"]].copy()
        tabelle["ts"] = tabelle["ts"].dt.strftime("%d.%m.%Y %H:%M:%S")
        tabelle.columns = ["Version", "Zeitpunkt", "Abonnenten", "Änderung"]
        st.dataframe(tabelle, hide_index=True, height=260)


def _render_dl_reports(result) -> None:
    """Gespiegelte Testreport-PDFs mit Anzeige- und Speichern-Button."""
    berichte = db.list_downloader_reports(result.id)
    if not berichte:
        st.info("Noch keine Testreport-PDFs gespiegelt. „Testberichte aktualisieren“ "
                "lädt sie aus dem MqlDownloader.")
        return
    for index, item in enumerate(berichte):
        key = f"dl_pdf_{result.id}_{item['version']}_{index}"
        pfad = Path(item["path"])
        visible_key = f"{key}_visible"
        visible = bool(st.session_state.get(visible_key))
        actions = st.container(horizontal=True, vertical_alignment="center")
        clicked = actions.button(
            "PDF schließen" if visible else f"{item['name']} anzeigen",
            key=key, icon=":material/picture_as_pdf:")
        groesse = (f"{item['size_bytes'] / 1024:.0f} kB"
                   if item.get("size_bytes") else "Größe unbekannt")
        stand = f" · Stand im Downloader: {item['last_modified']}" if item.get("last_modified") else ""
        actions.caption(f"{item['version']} · {groesse}{stand}")
        actions.download_button(
            "PDF speichern",
            data=(lambda p=pfad: p.read_bytes()) if pfad.exists() else b"",
            file_name=item["name"], mime="application/pdf",
            key=f"{key}_download", icon=":material/download:",
            disabled=not pfad.exists(), on_click="ignore")
        if clicked:
            visible = not visible
            st.session_state[visible_key] = visible
        if visible and pfad.exists():
            st.pdf(pfad, height=820, key=f"{key}_document")
        elif visible:
            st.warning("Die gespeicherte PDF-Datei fehlt auf der Platte. "
                       "Bitte „Testberichte aktualisieren“ erneut ausführen.")


def render_downloader_section(result) -> None:
    """Abonnenten-Verlauf + Testreport-PDFs aus dem MqlDownloader (REST, lesend)."""
    if not getattr(result, "id", 0):
        return
    section_header(
        "MqlDownloader",
        "Abonnenten-Verlauf und Testreport-PDFs aus dem lokalen Downloader-Netzwerkdienst.",
        help_key="downloader_section",
    )
    settings = config.load_settings()
    if not str(settings.get("downloader_base_url") or "").strip():
        st.info("Der MqlDownloader ist nicht angebunden. Base-URL im Admin-Bereich "
                "unter „MqlDownloader“ hinterlegen — danach lassen sich hier "
                "Abonnenten-Verlauf und Testreport-PDFs je Signal laden.",
                icon=":material/settings_ethernet:")
        return
    with st.container(border=True):
        actions = st.container(horizontal=True, vertical_alignment="center")
        if actions.button("Nutzer-Verlauf aktualisieren", key=f"dl_history_{result.id}",
                          icon=":material/timeline:"):
            try:
                neu = _dl_fetch_history(result)
                if not neu:
                    st.toast("Keine neuen Abonnenten-Datenpunkte.", icon=":material/check:")
            except downloader_client.DownloaderError as exc:
                st.error(f"Abonnenten-Verlauf konnte nicht geladen werden: {exc}")
        if actions.button("Testberichte aktualisieren", key=f"dl_reports_{result.id}",
                          icon=":material/cloud_download:"):
            try:
                if not _dl_fetch_reports(result):
                    st.toast("Keine neuen oder geänderten Testreport-PDFs.",
                             icon=":material/check:")
            except downloader_client.DownloaderError as exc:
                st.error(f"Testberichte konnten nicht geladen werden: {exc}")
        st.caption("Alles wird lokal gespiegelt (Ordner data/downloader/{Signal-ID} + "
                   "Datenbank) und bleibt auch anzeigbar, wenn der Downloader aus ist.")
        _render_dl_history(result)
        _render_dl_reports(result)


_DOK_ARTEN = (
    ("trade_analyse", "1 · Trade-Analyse"),
    ("risiko_analyse", "2 · Risiko-Analyse"),
    ("gesamtbericht", "3 · Gesamtbericht"),
    ("tiefenanalyse", "ℹ️ Erweiterte KI-Analyse (Tiefenanalyse)"),
)


def render_downloader_docs_panel(results) -> None:
    """Vom 📄-Icon in der Ergebnistabelle geöffnet: alle PDFs je Signal.

    Zwei Gruppen: die lokal erzeugten Bericht-PDFs (Trade-/Risiko-Analyse,
    Gesamtbericht, Tiefenanalyse) und die aus dem MqlDownloader gespiegelten
    Testreport-PDFs. Alles liegt in der Datenbank bzw. auf der Platte und
    bleibt damit über Sitzungen hinweg abrufbar.
    """
    doc_id = st.session_state.get("downloader_doc_signal_id")
    if doc_id is None:
        return
    identity = st.session_state.get("downloader_doc_identity")
    match = next((x for x in results
                  if identity is not None and _result_identity(x) == identity), None)
    if match is None:
        match = next((x for x in results if x.id == doc_id), None)
    if match is None:
        st.session_state.pop("downloader_doc_signal_id", None)
        st.session_state.pop("downloader_doc_identity", None)
        return
    berichte = db.list_downloader_reports(doc_id)
    eigene = [(art, label) for art, label in _DOK_ARTEN
              if getattr(match, art, "")]
    with st.container(border=True):
        kopf = st.container(horizontal=True, vertical_alignment="center")
        kopf.markdown(f"### :material/folder_open: Dokumente — {match.name} (#{doc_id})")
        with kopf:
            if action_button("Schließen", key=f"close_docs_{doc_id}",
                             help_key="downloader_docs"):
                st.session_state.pop("downloader_doc_signal_id", None)
                st.session_state.pop("downloader_doc_identity", None)
                st.rerun()
        if not berichte and not eigene:
            st.info("Weder eigene Bericht-PDFs noch gespiegelte Downloader-PDFs "
                    "vorhanden. KI-Berichte entstehen im Workflow bzw. per "
                    "„Erweiterte KI Analyse machen“ (Detailansicht); "
                    "Downloader-PDFs über den MqlDownloader-Abgleich.")
            return
        if eigene:
            st.markdown("**Eigene Berichte**")
            for art, label in eigene:
                render_result_pdf_viewer(
                    match, art,
                    key=f"docs_panel_lokal_{art}_{_result_snapshot_token(match)}",
                    label=f"{label} anzeigen")
        if berichte:
            st.markdown("**Testreport-PDFs (MqlDownloader-Spiegel)**")
            for index, item in enumerate(berichte):
                key = f"docs_panel_{doc_id}_{index}"
                pfad = Path(item["path"])
                groesse_kb = (item["size_bytes"] / 1024
                              if item.get("size_bytes") else 0)
                groesse = (f"{groesse_kb:.0f} kB" if item.get("size_bytes")
                           else "Größe unbekannt")
                lang = groesse_kb >= _LANG_KB
                _gelbe_anzeige(key, lang)
                stand = (f" · Stand im Downloader: {item['last_modified']}"
                         if item.get("last_modified") else "")
                visible_key = f"{key}_visible"
                visible = bool(st.session_state.get(visible_key))
                aktionen = st.container(horizontal=True, vertical_alignment="center")
                aktionen.markdown(f"**{item['name']}**")
                aktionen.caption(f"{item['version']} · {groesse}{stand}")
                geklickt = aktionen.button(
                    "PDF schließen" if visible else f"{item['name']} anzeigen",
                    key=key, icon=":material/picture_as_pdf:",
                    help="Langes Dokument — gelb markiert." if lang else None)
                aktionen.download_button(
                    "PDF speichern",
                    data=(lambda p=pfad: p.read_bytes()) if pfad.exists() else b"",
                    file_name=item["name"], mime="application/pdf",
                    key=f"{key}_download",
                    icon=":material/download:",
                    disabled=not pfad.exists(), on_click="ignore")
                if geklickt:
                    visible = not visible
                    st.session_state[visible_key] = visible
                if visible and pfad.exists():
                    st.pdf(pfad, height=820, key=f"{key}_document")
                elif visible:
                    st.warning("Die Datei fehlt auf der Platte — Abgleich erneut "
                               "ausführen.")


def render_detail(result) -> None:
    """Detailansicht eines ScanResults: Kennzahlen, Teilergebnisse, Bericht."""
    row = result.to_row()
    gewinn_monat = row.get("Gewinn %/Monat")
    retdd = row.get("RetDD")
    settings = config.load_settings()
    dd_limit = settings.get("schranke_eq_dd_pct", 30.0)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(f"{result.ampel} {result.name} · #{result.id}")
        if result.url:
            st.link_button("Auf MQL5 öffnen", result.url, icon=":material/open_in_new:")

    # Fix-Checkmark (Nutzer-Wunsch 28.09.2026): Signal-ID für JEDEN Scan pinnen.
    # Der Widget-Key enthält den aktuellen Zustand — ändert sich der Zustand
    # woanders (z. B. über die Fix-IDs-Verwaltung), entsteht ein frisches
    # Widget mit richtigem Häkchen statt eines veralteten Klicks.
    if getattr(result, "source_kind", "live") == "live" and result.id:
        fix_ist = result.id in fix_signale.fix_ids()
        fix_neu = st.checkbox(
            "📌 Fix — immer scannen", value=fix_ist,
            key=f"fix_check_{result.id}_{int(fix_ist)}",
            help="Setzt diese Signal-ID auf die Immer-Scannen-Liste: Jeder Scan "
                 "(Full-Scan, Teilscan, autonome Scans) prüft das Signal — auch "
                 "wenn es aus den MQL5-Top-Listen rutscht, die Wochen-/Abonnenten-"
                 "Vorfilter nicht bestehen oder die Export-Auswahl (top N) voll ist. "
                 "Kein Vorzugsurteil: Ampel und Score gelten unverändert.")
        if fix_neu != fix_ist:
            fix_signale.setzen(result.id, fix_neu)
            st.toast(f"#{result.id} " + ("ist jetzt Fix — wird in jedem Scan geprüft"
                                         if fix_neu else "ist kein Fix-Signal mehr"),
                     icon=":material/push_pin:")
            st.rerun()

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
            dd_farbe = _max_drawdown_farbe(result.max_drawdown_equity_pct, dd_limit)
            if result.schranke_verletzt:
                dd_farbe = "red"
            st.badge(
                "Drawdown-Grenze überschritten" if result.schranke_verletzt else
                "Equity-DD unbelegt" if dd_farbe == "gray" else
                ("Equity-DD über Grenze" if dd_farbe == "red" else
                 "Equity-DD nahe Grenze" if dd_farbe == "orange" else
                 "Equity-DD mit Puffer"), color=dd_farbe)
            st.badge(
                "Ertragsziel erreicht"
                if gewinn_monat is not None and gewinn_monat >= settings.get("min_ertrag_pct_monat", 5.0)
                else "Ertragsziel nicht belegt",
                color="green"
                if gewinn_monat is not None and gewinn_monat >= settings.get("min_ertrag_pct_monat", 5.0)
                else "gray",
            )
        st.markdown("**Urteil**")
        st.write(result.urteil or "Noch kein belastbares Urteil vorhanden.")

    # Stilbruch-Historie aus dem Agenten-Dossier — dauerhaft mit dem Signal
    # verknüpft (Nutzer-Wunsch 22.09.2026): bleibt sichtbar, auch wenn die
    # Ampel später z. B. von 🟡 auf 🟢 wechselt; das Ampel-Urteil sagt nur
    # den heutigen Stand.
    from .agenten import dossier as dossier_db
    stilbrueche = dossier_db.stilbruch_historie(result.id)
    if stilbrueche:
        letztes_datum = str(stilbrueche[0]["ts"] or "")[:10]
        with st.container(border=True):
            st.warning(
                f"**Stilbruch-Historie:** {len(stilbrueche)} "
                f"{'Stilbruch' if len(stilbrueche) == 1 else 'Stilbrüche'} "
                f"erkannt (zuletzt {letztes_datum}) — der Signal-Betreuer hat "
                f"Abweichungen vom eigenen Algo-Profil festgestellt. Dieses "
                f"Warnfeld bleibt unabhängig vom Ampel-Urteil stehen, auch "
                f"nach einem Wechsel auf 🟢.", icon=":material/warning:")
            with st.expander("Stilbruch-Beobachtungen des Betreuers (Dossier)",
                             expanded=False, icon=":material/manage_search:"):
                for b in stilbrueche:
                    st.caption(str(b["ts"]))
                    st.markdown(str(b["text"] or ""))

    if result.ampel == "⛔":
        eintrag = regelwerk.ausgeschlossen_eintrag(result.id)
        grund = (eintrag or {}).get("grund", "")
        with st.container(border=True):
            section_header("Regelwerk · Ausschlussliste",
                           "Warum steht dieses Signal auf der Liste?",
                           help_key="ausschlussliste",
                           # Gleicher help_key wie im Seiten-Aufklapper — ohne
                           # eigenen Key würde der ⓘ-Button doppelt registriert.
                           key="section_ausschlussliste_detail")
            if grund:
                st.markdown(f"**Gemessener Grund:** {_html.escape(grund)}")
            with st.expander("Vollständiges Regelwerk anzeigen",
                             expanded=False, icon=":material/gavel:"):
                st.markdown(regelwerk.regelwerk_markdown())

    with st.container(border=True):
        section_header("Schutz und Stop-Nachweis", "Kernfrage: bewiesen oder nur behauptet?",
                       help_key="stop_evidence")
        st.markdown(result.stop_nachweis
                   or "SL nicht übertragen — neutral; die KI-Analyse schätzt aus dem Verhalten ab.")

    section_header("Risiko und Ertrag", "Historische Kennzahlen · fehlende Daten erscheinen als Strich.", help_key="risk_metrics")
    with st.container(horizontal=True):
        st.metric("Risiko-Score", f"{result.score:.1f}" if result.score is not None else "—",
                  border=True)
        st.metric("Max-Drawdown (Equity, gemessen)",
                  f"{result.max_drawdown_equity_pct:.1f} %" if result.max_drawdown_equity_pct is not None else "—",
                  border=True)
        st.metric("Gewinn %/Monat",
                  f"{gewinn_monat:.2f} %" if gewinn_monat is not None else "—",
                  help="Eigene geometrische Monatsrendite aus den Trade-Daten.",
                  border=True)
        st.metric("RetDD",
                  f"{retdd:.2f}" if retdd is not None else "—",
                  help="Gewinn %/Monat ÷ gemessener Max-Drawdown % (Equity). "
                       "Fehlende oder nullprozentige Equity-Messung liefert kein Verhältnis.",
                  border=True)
        st.metric("Trading-DD (geschlossen)",
                  f"{result.trading_dd_pct:.1f} %" if result.trading_dd_pct is not None else "—",
                  border=True)
        st.metric("Drawdown (Plattform)",
                  f"{result.dd_equity_pct:.1f} %" if result.dd_equity_pct is not None else "—",
                  border=True)
        st.metric("Ertrag / Monat (Plattform)",
                  f"{result.ertrag_monat_pct:.1f} %" if result.ertrag_monat_pct is not None else "—",
                  border=True)

    if result.max_drawdown_equity_pct is None:
        st.warning(result.equity_messung_status + ". Der Trading-DD enthält "
                   "keine zwischenzeitlichen offenen Gewinne oder Verluste.",
                   icon=":material/monitoring:")
    else:
        st.caption(result.equity_messung_status + " · Die Drawdown-Schranke "
                   "berücksichtigt zusätzlich beide Plattformwerte und den Trading-DD.")
    if result.identische_tradezeilen:
        st.caption(f"Trade-Daten: {result.identische_tradezeilen} identische Zeilen "
                   "sind vollständig enthalten. Der Export hat keine Ticket-IDs; "
                   "gleiche Zeilen können verschiedene echte Positionen darstellen.")

    # Equity-DD-Studie (Nutzer-Wunsch 03.10.2026): On-Demand-Nachmessung für
    # dieses Signal — gleiche Messung wie der Tabellen-Button, hier mit dem
    # Kontext der Detailansicht.
    if st.button("Equity-DD-Studie öffnen — aus echten Kursen nachgemessen",
                 key=f"eqdd_detail_{_result_snapshot_token(result)}",
                 icon=":material/monitoring:",
                 help="Misst den Equity-Drawdown stundenfein nach: realisierter "
                      "Betrag und offener Betrag (floating) je Stunde, Kurse vom "
                      "MT5-Referenzterminal, GMT-Abgleich je Währungspaar. "
                      "Dauert einige Sekunden; Fenster mit Chart und Risiko-Texten."):
        from .equity_studie_ui import equity_studie_dialog
        equity_studie_dialog(result)

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

    with st.container(border=True):
        section_header(
            "Erweiterte KI-Analyse (Tiefenanalyse)",
            "Manuelle Vollanalyse: vollständige Trade-Daten + Signal-Kennzahlen "
            "an das starke Modell. Verbraucht Tokens und dauert einige Minuten.",
            help_key="tiefenanalyse",
        )
        if action_button(
                "Erweiterte KI Analyse machen",
                key=f"tiefe_start_{_result_snapshot_token(result)}",
                help_key="tiefenanalyse_start", type="primary",
                icon=":material/psychology:"):
            banner = aktivitaets_banner("Erweiterte KI-Analyse läuft …")
            with st.status("Erweiterte KI-Analyse läuft — bitte Fenster offen lassen.",
                           expanded=True) as status:
                try:
                    llm_runner.run_tiefenanalyse_einzeln(
                        result, log=lambda m: st.write(m))
                    status.update(label="Erweiterte KI-Analyse fertig — "
                                  "PDF und Text stehen unten bereit.",
                                  state="complete", expanded=False)
                except Exception as exc:
                    status.update(label="Erweiterte KI-Analyse fehlgeschlagen",
                                  state="error", expanded=False)
                    st.error(str(exc))
                finally:
                    banner.empty()
        if result.tiefenanalyse:
            render_result_pdf_viewer(
                result, "tiefenanalyse",
                key=f"detail_tiefe_{_result_snapshot_token(result)}",
                label="Tiefenanalyse-PDF anzeigen", type="primary")
            st.caption(f"Stand: {result.tiefenanalyse_at or '—'} · "
                       f"Modell: {result.tiefenanalyse_model or '—'}")
            with st.expander("Text der Erweiterten KI-Analyse",
                             icon=":material/notes:"):
                st.markdown(urteile_farbig(result.tiefenanalyse),
                            unsafe_allow_html=True)
        else:
            st.info("In dieser Quelle ist keine Erweiterte KI-Analyse enthalten. "
                    "Sitzung und Archiv sind Momentaufnahmen und nehmen später "
                    "erstellte Analysen nicht auf — wechsle zur Quelle "
                    "„Datenbank (alle Berichte)“, oder starte sie hier per "
                    "„Erweiterte KI Analyse machen“.", icon=":material/history:")

    render_downloader_section(result)
