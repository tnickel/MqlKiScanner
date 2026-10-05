# -*- coding: utf-8 -*-
"""UI-Bausteine der Seite „Alle Signale“ (Nutzer-Wunsch 05.10.2026).

Trennung wie bei der Equity-Studie: Diagramm- und Zeilen-Builder sind reine
Funktionen (ohne Streamlit-Laufzeit testbar), render_detail baut die Detail-
ansicht unter der Tabelle. Die Equity-Studie selbst (render_studie) wird
unverändert aus equity_studie_ui eingebunden — der floating-inklusive
Max-Drawdown bleibt dort exklusiv.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from . import signal_statistik

# Farbwelt wie Equity-Studie (dunkles Theme verträgt diese Töne am besten).
_FARBE_POSITIV = "#2e7d32"
_FARBE_NEGATIV = "#d32f2f"
_FARBE_KURVE = "#1f6feb"


@st.cache_data(show_spinner=False)
def _tradeliste_cached(trades_pfad: str, sha: str) -> list[dict]:
    """Tradeliste je (Pfad, SHA) cachen — 15k-Zeilen-Listen nicht je Rerun
    neu parsen; der SHA verhindert veraltete Caches nach Neu-Lieferung."""
    return signal_statistik.tradeliste(trades_pfad, {})

# Kapitalbasis-Kürzel für die Tabellenspalte „Basis“.
BASIS_KUERZEL = {
    "csv_einzahlungen": "CSV",
    "signalseite_initial_deposit": "Seite",
    "implizit_aus_balance": "implizit",
    "virtuelle_annahme": "virtuell",
    "extern": "extern",
}

BASIS_LANGTEXT = {
    "CSV": "CSV-Einzahlungen im Export",
    "Seite": "Signalseite „Initial Deposit“",
    "implizit": "implizit: Web-Balance − Trade-Netto",
    "virtuell": "virtuelle Annahme aus dem Quellen-Monitor (10.000 USD)",
    "extern": "extern übergeben",
}


def _de(wert, nachstellen: int = 2) -> str:
    """Zahl deutsch formatieren (1.234,56)."""
    if wert is None:
        return "—"
    text = f"{float(wert):,.{nachstellen}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def basis_kuerzel(quelle: str | None) -> str:
    return BASIS_KUERZEL.get(quelle or "", "—")


def tabellen_zeile(result, statistik: dict | None) -> dict:
    """Eine Tabellenzeile (reine Funktion) — Katalog- und Vorstufenwerte."""
    statistik = statistik or {}
    return {
        "Ampel": getattr(result, "ampel", "") or "—",
        "Fix": "📌 FIX" if getattr(result, "id", None) in _fix_ids() else "",
        "Name": getattr(result, "name", "") or str(getattr(result, "id", "")),
        "Quelle": getattr(result, "quelle", "mql5") or "mql5",
        "Plattform": getattr(result, "platform", "") or "",
        "ID": getattr(result, "id", None),
        "Wochen": getattr(result, "wochen", None),
        "Abonnenten": getattr(result, "abonnenten", None),
        "Drawdown % (Plattform)": getattr(result, "dd_equity_pct", None),
        "Ertrag %/M (Plattform)": getattr(result, "ertrag_monat_pct", None),
        "Gewinn %/M (geom.)": statistik.get("ertrag_monat_geom_pct"),
        "Trading-DD % (Trades)": statistik.get("trading_dd_pct"),
        "RetDD": getattr(result, "retdd_monat", None),
        "RetDD (Vorbehalt)": getattr(result, "retdd_monat_vorbehalt", None),
        "Profitfaktor": statistik.get("profit_faktor"),
        "Winrate %": statistik.get("winrate_pct"),
        "Trades": statistik.get("trades"),
        "Basis": basis_kuerzel(statistik.get("kapitalbasis_quelle"))
        if statistik.get("kapitalbasis_ok") else "—",
        "Forensik": "✓" if getattr(result, "forensik_vorhanden", False) else "—",
    }


def _fix_ids() -> set:
    """Fix-IDs lazy laden (Importfehler/leer darf die Tabelle nie brechen)."""
    try:
        from . import fix_signale
        return fix_signale.fix_ids()
    except Exception:
        return set()


def monats_balken_chart(statistik: dict) -> go.Figure:
    """Monatliche Gewinnprozente als Balken (grün/rot), Netto im Hover."""
    monate = statistik.get("monate_pct") or {}
    usd = statistik.get("monate_usd") or {}
    x = list(monate)
    y = [monate[m] for m in x]
    fig = go.Figure(go.Bar(
        x=x, y=y,
        marker_color=[_FARBE_POSITIV if v >= 0 else _FARBE_NEGATIV for v in y],
        customdata=[usd.get(m) for m in x],
        hovertemplate="%{x}<br>%{y:.2f} % · Netto %{customdata:,.2f} USD"
                      "<extra></extra>",
    ))
    fig.update_layout(
        height=440, template="plotly_white", margin={"l": 56, "r": 14, "t": 8, "b": 8},
        hovermode="x unified", showlegend=False,
        yaxis={"title": "% je Monat", "zeroline": True, "zerolinecolor": "#9e9e9e"},
        xaxis={"tickangle": -45},
    )
    return fig


def kurve_unterwasser_chart(statistik: dict) -> go.Figure:
    """Virtuelle Trading-Kurve oben, Unterwasser-Verlauf unten.

    Unterwasser-Konvention wie die Equity-Studie: NEGATIVE Werte, die Kurve
    hängt unter der Nulllinie nach unten — je tiefer, desto größer der
    Rückgang unter den letzten Höchststand ((Stand/Hoch − 1) × 100).
    """
    kurve = statistik.get("kurve") or []
    x = [p[0] for p in kurve]
    y = [p[1] for p in kurve]
    unterwasser: list[float] = []
    spitze = float("-inf")
    for stand in y:
        spitze = max(spitze, stand)
        unterwasser.append((stand / spitze - 1.0) * 100.0 if spitze > 0 else 0.0)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.62, 0.38], vertical_spacing=0.08,
                        subplot_titles=("Virtuelles Konto (geschlossene Trades)",
                                        "Unterwasser — Abstand zum letzten Höchststand"))
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines", name="Kontostand",
        line={"color": _FARBE_KURVE, "width": 2},
        hovertemplate="%{x}<br>%{y:,.2f} USD<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=unterwasser, mode="lines", name="Unterwasser",
        line={"color": _FARBE_NEGATIV, "width": 1.5}, fill="tozeroy",
        fillcolor="rgba(211,47,47,0.18)",
        hovertemplate="%{x}<br>%{y:.2f} %<extra></extra>"), row=2, col=1)
    fig.update_layout(
        height=440, template="plotly_white", margin={"l": 56, "r": 14, "t": 8, "b": 8},
        hovermode="x unified", showlegend=False,
    )
    fig.update_yaxes(title_text="USD", tickformat=",.0f", row=1, col=1)
    fig.update_yaxes(title_text="%", row=2, col=1, ticksuffix=" %")
    return fig


def dauer_balken_chart(dauer_statistik: dict) -> go.Figure:
    """Haltezeit-Verteilung als horizontale Balken (Nutzer 05.10.: Scalper
    abschätzen). Die GEFAEHRLICHEN Buckets (0 Sek, <1 Min) rot markiert —
    beim Kopieren möglicherweise nicht erreichbar (Latenz/Slippage)."""
    buckets = list(reversed(dauer_statistik.get("buckets") or []))
    namen = [b["bucket"] for b in buckets]
    anzahl = [b["anzahl"] for b in buckets]
    farben = ["#d32f2f" if b.get("gefaehrlich") else "#1f6feb" for b in buckets]
    custom = [(b["anteil_pct"], b["netto_usd"]) for b in buckets]
    fig = go.Figure(go.Bar(
        y=namen, x=anzahl, orientation="h", marker_color=farben,
        customdata=custom,
        hovertemplate="%{y}<br>%{x} Trades (%{customdata[0]:.1f} %)"
                      "<br>Netto %{customdata[1]:,.2f} USD<extra></extra>",
    ))
    fig.update_layout(
        height=380, template="plotly_white", margin={"l": 90, "r": 14, "t": 8, "b": 8},
        hovermode="y unified", showlegend=False,
        xaxis={"title": "Trades", "tickformat": ",.0f"},
        yaxis={"title": None},
    )
    return fig


def _kpi(behälter, label: str, wert, hilfe: str | None = None) -> None:
    with behälter:
        if hilfe:
            st.metric(label, wert, border=True, help=hilfe)
        else:
            st.metric(label, wert, border=True)


def render_detail(auswahl, statistik: dict | None, *, key_prefix: str = "detail") -> None:
    """Detailansicht unter der Tabelle — Karten, Charts, Monats-/Symboltabellen.

    Bewusst reine Anzeige: kein Urteil, keine Ampel-Neuberechnung. Der
    floating-inklusive Max-Drawdown ist über den Studien-Button erreichbar
    (equity_studie_ui.render_studie, unverändert).
    """
    statistik = statistik or {}
    name = getattr(auswahl, "name", "") or f"#{getattr(auswahl, 'id', '?')}"
    url = getattr(auswahl, "url", "") or ""
    st.subheader(f"{getattr(auswahl, 'ampel', '')} {name}".strip())
    zeile = f"#{getattr(auswahl, 'id', '?')} · Quelle {getattr(auswahl, 'quelle', 'mql5') or 'mql5'}"
    broker = getattr(auswahl, "broker_server", None)
    if broker:
        zeile += f" · Broker {broker}"
    st.caption(zeile)
    if url:
        st.page_link(url, label="Signal beim Anbieter öffnen", icon=":material/open_in_new:")

    if statistik.get("fehler"):
        st.warning(f"Statistik nicht berechenbar: {statistik['fehler']}",
                   icon=":material/warning:")
        return

    st.info(
        "**Unabhängige Vorstufe — rein aus dem Trade-Cache gerechnet.** "
        "Kurve und Trading-DD enthalten nur GESCHLOSSENE Trades: offenes "
        "Floating fehlt, der echte Max-Drawdown kann höher liegen (Button "
        "unten). Ampel und Urteil bleiben beim Workflow — diese Ansicht "
        "bewertet nichts.", icon=":material/functions:")

    basis_ok = statistik.get("kapitalbasis_ok")
    if not basis_ok:
        st.caption("Keine belegbare Kapitalbasis (kein Initial Deposit, keine "
                   "Web-Balance) — Prozentwerte entfallen, USD-Werte bleiben.")

    with st.container(horizontal=True):
        _kpi(st.container(), "Gewinn %/Monat (geom.)",
             _de(statistik.get("ertrag_monat_geom_pct")),
             "Geometrisches Monatsmittel der virtuellen Kurve (zinseszins-wahr)")
        _kpi(st.container(), "CAGR %/Jahr", _de(statistik.get("cagr_jahr_pct")))
        _kpi(st.container(), "Profitfaktor", _de(statistik.get("profit_faktor")))
        _kpi(st.container(), "Winrate %", _de(statistik.get("winrate_pct"), 1))
        _kpi(st.container(), "Trades", _de(statistik.get("trades"), 0))
    with st.container(horizontal=True):
        _kpi(st.container(), "Trading-DD % (Trades)",
             _de(statistik.get("trading_dd_pct")),
             "Größter Rückgang der Kurve GESCHLOSSENER Trades — ohne Floating")
        _kpi(st.container(), "Trading-DD USD", _de(statistik.get("trading_dd_usd")))
        _kpi(st.container(), "Netto gesamt USD", _de(statistik.get("netto_gesamt_usd")))
        _kpi(st.container(), "Endstand virtuell USD",
             _de(statistik.get("endstand_virtuell_usd")))
        retdd_ok = getattr(auswahl, "retdd_monat", None)
        retdd_vorbehalt = getattr(auswahl, "retdd_monat_vorbehalt", None)
        if retdd_ok is not None:
            _kpi(st.container(), "RetDD", _de(retdd_ok),
                 "Gewinn %/Monat ÷ belastbar gemessener Max-Drawdown % "
                 "(Equity inkl. Floating) — Mindestqualität 1,0")
        elif retdd_vorbehalt is not None:
            _kpi(st.container(), "RetDD (Vorbehalt)",
                 "≈ " + _de(retdd_vorbehalt),
                 "ORANGE/VORBEHALT: Gewinn %/Monat ÷ roher Kurs-Max-DD, dessen "
                 "Zeitbasis/Kursabdeckung die Verlässlichkeitsprüfung NICHT "
                 "bestanden hat. Nur orientierend — ohne belastbare Messung "
                 "gibt es kein Grün")
        else:
            _kpi(st.container(), "Ertrag je Close-DD ⚠",
                 _de(statistik.get("ertrag_je_close_dd")),
                 "VORBEWERTUNG: geom. Ertrag ÷ Trading-DD. Kein RetDD — dessen "
                 "Nenner darf nur der floating-inklusive Max-Drawdown sein")

    if (retdd_ok is None and retdd_vorbehalt is not None
            and getattr(auswahl, "equity_dd_rekon_roh_pct", None) is not None):
        st.markdown(
            f":orange[**RetDD (Vorbehalt) ≈ {_de(retdd_vorbehalt)}:**] gerechnet "
            f"mit dem ROHEN Kurs-Max-DD {_de(auswahl.equity_dd_rekon_roh_pct, 1)} %, "
            "dessen Messung die Verlässlichkeitsprüfung nicht bestanden hat — "
            f"{getattr(auswahl, 'retdd_vorbehalt_grund', '') or 'Zeitbasis/Kursabdeckung unzuverlässig'}. "
            "Der Wert ist nur eine Orientierung (orange); ohne belastbare "
            "Kursmessung gibt es kein Grün.")

    if statistik.get("martingale_flag"):
        st.warning(f"Martingale-Signatur: {statistik.get('martingale_text')}",
                   icon=":material/trending_up:")
    else:
        st.caption(f"Lot-Verhalten: {statistik.get('martingale_text') or '—'}")

    basis_text = BASIS_LANGTEXT.get(basis_kuerzel(statistik.get("kapitalbasis_quelle")),
                                    statistik.get("kapitalbasis_quelle") or "unbekannt")
    st.caption(f"Kapitalbasis: {basis_text}"
               + (f" · {_de(statistik.get('kapitalbasis_usd'), 0)} USD"
                  if basis_ok else "")
               + (f" · Zeitspanne {str(statistik.get('zeit_von', ''))[:10]} bis "
                  f"{str(statistik.get('zeit_bis', ''))[:10]}"
                  f" ({_de(statistik.get('dauer_monate'), 1)} Monate)"
                  if statistik.get("zeit_von") else ""))

    if statistik.get("monate_pct"):
        links, rechts = st.columns(2)
        with links:
            st.caption("**Monatliche Gewinnprozente**")
            st.plotly_chart(monats_balken_chart(statistik), width="stretch",
                            key=f"{key_prefix}_monate")
        with rechts:
            st.caption("**Konto-Kurve mit Unterwasser-DD**")
            st.plotly_chart(kurve_unterwasser_chart(statistik), width="stretch",
                            key=f"{key_prefix}_kurve")

    with st.expander("Monats-Tabelle", expanded=False, icon=":material/table_rows:"):
        monate = statistik.get("monate_pct") or {}
        usd = statistik.get("monate_usd") or {}
        if monate:
            zeilen = []
            kumuliert = 0.0
            for monat in sorted(monate, reverse=True):
                kumuliert += monate[monat]
                zeilen.append({
                    "Monat": monat,
                    "Netto USD": round(usd.get(monat, 0.0), 2),
                    "Rendite %": round(monate[monat], 2),
                    "Kumuliert %": round(kumuliert, 2),
                })
            st.dataframe(zeilen, hide_index=True, width="stretch")
        else:
            st.caption("Keine Monatsrenditen (ohne Kapitalbasis).")

    per_symbol = statistik.get("per_symbol") or {}
    if per_symbol:
        with st.expander(f"Symbole ({len(per_symbol)})", expanded=False,
                         icon=":material/candlestick_chart:"):
            st.dataframe([{
                "Symbol": sym,
                "Trades": werte.get("trades"),
                "Netto USD": werte.get("net"),
                "Winrate %": werte.get("winrate_pct"),
                "Lots min/max": f"{werte.get('lots_min')}–{werte.get('lots_max')}",
            } for sym, werte in sorted(per_symbol.items(),
                                       key=lambda kv: -kv[1].get("trades", 0))],
                hide_index=True, width="stretch")

    # ── Tradeliste + Haltezeit-Statistik (Nutzer-Wunsch 05.10.) ────────────
    st.divider()
    schalter_tl = f"{key_prefix}_tradeliste_offen"
    ds = statistik.get("dauer_statistik") or {}
    if st.button("📋 Tradeliste + Haltezeit-Statistik",
                 key=f"{key_prefix}_tradeliste_button", icon=":material/receipt_long:",
                 help="Verteilung der Haltezeiten (Scalper-Erkennung) und die "
                      "komplette Tradeliste aus dem Cache. Haltezeiten unter "
                      "einer Minute sind beim Kopieren gefährlich: Die eigene "
                      "Kopie erreicht solche Fills wegen Latenz/Slippage "
                      "möglicherweise gar nicht."):
        st.session_state[schalter_tl] = not st.session_state.get(schalter_tl, False)
    if st.session_state.get(schalter_tl) and ds:
        if ds.get("gefaehrlich_anzahl"):
            st.warning(
                f"**⚠ {ds['gefaehrlich_anzahl']} Trades "
                f"({ds.get('gefaehrlich_anteil_pct', 0.0):.1f} %) dauerten "
                "0 Sekunden oder unter einer Minute.** Beim Kopieren solcher "
                "Signale sind diese Trades mit eigener Latenz und Slippage "
                "möglicherweise NICHT erreichbar — die eigene Kopie kann die "
                "Ergebnisse dann nicht reproduzieren. Für Scalper gilt: "
                "je höher dieser Anteil, desto kritischer.",
                icon=":material/timer:")
        st.caption(
            f"Median-Haltezeit {signal_statistik.dauer_text(ds.get('dauer_median_s') or 0.0)} · "
            f"längste {signal_statistik.dauer_text(ds.get('dauer_max_s') or 0.0)} · "
            f"{ds.get('null_sek', 0)}× 0 Sekunden · {ds.get('unter_1min', 0)}× unter 1 Minute")
        st.plotly_chart(dauer_balken_chart(ds), width="stretch",
                        key=f"{key_prefix}_dauer")
        pfad = getattr(auswahl, "trades_path", "") or ""
        if pfad and Path(pfad).exists():
            zeilen = _tradeliste_cached(
                pfad, getattr(auswahl, "trades_sha256", "") or "kein-sha")
            st.dataframe(zeilen, hide_index=True, height=420,
                         width="stretch", key=f"{key_prefix}_tradeliste")
            csv = pd.DataFrame(zeilen).to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button("Tradeliste als CSV", csv,
                               f"tradeliste_{getattr(auswahl, 'id', 'x')}.csv",
                               'text/csv', key=f"{key_prefix}_tradeliste_csv",
                               icon=":material/download:")

    # ── Max-DD aus Kursen: die Equity-Studie unverändert einbinden ─────────
    st.divider()
    schalter = f"{key_prefix}_studie_offen"
    if st.button("🔬 Max-DD aus Kursen berechnen (Equity-Studie)",
                 key=f"{key_prefix}_studie_button", icon=":material/science:",
                 help="Startet die bekannte Studie: H1-Kurse je Symbol, GMT-"
                      "Abgleich, Equity inkl. Floating — floating-getreuer "
                      "Max-Drawdown mit Fortschrittsanzeige."):
        st.session_state[schalter] = True
    if st.session_state.get(schalter):
        # Kapitalbasis-Lücke schließen: never gescannte Quellen-Signale haben
        # keine Forensik — die Studien-Berechnung nimmt die Basis vom Result.
        if getattr(auswahl, "kapitalbasis_verwendet_usd", None) is None and basis_ok:
            auswahl.kapitalbasis_verwendet_usd = statistik.get("kapitalbasis_usd")
            auswahl.kapitalbasis_verwendet_quelle = statistik.get("kapitalbasis_quelle") or ""
        from .equity_studie_ui import render_studie
        render_studie(auswahl, key_prefix=f"{key_prefix}_studie")
