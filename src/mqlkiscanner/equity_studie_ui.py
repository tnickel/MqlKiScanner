# -*- coding: utf-8 -*-
"""GUI der Equity-DD-Studie (Nutzer-Wunsch 03.10.2026).

Öffnet die On-Demand-Nachmessung des Equity-Drawdowns für EIN Signal:
Button in der Ergebnisstabelle (ButtonColumn) und in der Detailansicht
öffnen den Dialog; die eigene Seite equity_studie.py zeigt dieselbe
Ansicht in voller Breite. Die Messung selbst rechnet equity_studie.studie
(Code, kein LLM); hier wird nur angezeigt — Ampel/Score/Urteil der Engine
bleiben verbindlich und unverändert.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from . import config, kursdaten, parser, scan_worker
from .equity_studie import studie
from .forensics import drawdown

# Plotly-Modebar: Zoom/Pan sind Standard; dazu Zeichenwerkzeuge (Linien/
# Rechtecke) und Radzoom — professionelle Chart-Bedienung im Dialog.
_CHART_CONFIG = {
    "scrollZoom": True,
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "eraseshape"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}
_FARBE_EQUITY = "#1f6feb"
_FARBE_REALISIERT = "#2e7d32"
_FARBE_FLOATING = "#d32f2f"


def _cache_key(result) -> str:
    sha = getattr(result, "trades_sha256", "") or ""
    return f"eqdd_studie_zeitbasis_v10_{result.id}_{sha[:12] or 'nosha'}"


def berechne(result, progress) -> dict:
    """Studie für ein ScanResult rechnen: CSV laden → Kapitalbasis → Kurse → Kurve.

    Wirft RuntimeError mit klarem Text, wenn die Trade-Datei fehlt oder das
    Kurs-Terminal nicht verfügbar ist. progress: callback(anteil_0_1, text).
    """
    progress(0.02, "Trade-Liste laden …")
    pfad = (getattr(result, "trades_path", "") or "").strip()
    if not pfad or not Path(pfad).exists():
        raise RuntimeError(
            f"Trade-Datei fehlt oder existiert nicht mehr: {pfad or '—'}. "
            "Die Studie braucht die gelieferte Trade-Liste (Cache des letzten "
            "Scans) — bitte das Signal neu scannen (z. B. Teilscan), danach "
            "steht die Datei wieder bereit.")
    parsed = parser.load_export(pfad)

    progress(0.08, "Kapitalbasis ermitteln …")
    # Dieselbe Auflösung wie die Forensik: CSV-Einzahlungen gewinnen, sonst
    # der extern belegte Wert (Initial Deposit Signalseite bzw. die von der
    # Pipeline tatsächlich verwendete Basis aus dem Forensik-Snapshot).
    extern = getattr(result, "kapitalbasis_verwendet_usd", None) \
        or getattr(result, "kapitalbasis_usd", None)
    quelle = getattr(result, "kapitalbasis_verwendet_quelle", "") \
        or "signalseite_initial_deposit"
    dd = drawdown.run(parsed, kapitalbasis_usd=extern, kapitalbasis_quelle=quelle)
    startkapital = float(dd.get("startkapital") or 0.0)

    progress(0.10, "MT5-Referenzterminal verbinden (Kurse, kann einige Sekunden dauern) …")
    settings = config.load_settings()
    anbieter = kursdaten.KursDaten(settings)
    ok, grund = anbieter.starten()
    if not ok:
        raise RuntimeError(f"Kursdaten nicht verfügbar: {grund}")
    try:
        daten = studie(
            parsed, anbieter, startkapital,
            broker=getattr(result, "broker_server", None) or None,
            progress=lambda a, t: progress(0.10 + 0.88 * a, t))
    finally:
        anbieter.beenden()

    daten["meta"] = {
        "name": getattr(result, "name", "") or f"#{result.id}",
        "signal_id": result.id,
        "quelle": getattr(result, "quelle", "mql5") or "mql5",
        "trades_pfad": pfad,
        "startkapital_quelle": dd.get("startkapital_quelle") or "unbekannt",
    }
    return daten


def _als_datetime(epoch_wert: int | None):
    if epoch_wert is None:
        return None
    return dt.datetime.fromtimestamp(int(epoch_wert), dt.timezone.utc)


def _chart(daten: dict, startkapital: float, schranke: float) -> go.Figure:
    """Equity/Realisiert/Floating oben, Unterwasser-Kurve unten, Rangeslider."""
    punkte = daten["punkte"]
    k = daten["kennzahlen"]
    x = [_als_datetime(p["t"]) for p in punkte]
    equity = [p["equity"] for p in punkte]
    realisiert = [p["realisiert"] for p in punkte]
    floating = [p["floating"] for p in punkte]

    # Unterwasser (% unter dem laufenden Hoch) auf Messpunkten.
    hoch = None
    unterwasser: list[float | None] = []
    for p in punkte:
        if not p["messpunkt"] or p["equity"] is None:
            unterwasser.append(None)
            continue
        wert = p["equity"]
        hoch = wert if hoch is None or wert > hoch else hoch
        unterwasser.append((wert / hoch - 1.0) * 100.0 if hoch > 0 else None)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.74, 0.26], vertical_spacing=0.04,
        subplot_titles=("Virtuelle Trading-Kurve: realisiert · Equity (inkl. Floating)",
                        "Unterwasser — Abstand zum letzten Höchststand"))
    fig.add_trace(go.Scatter(
        x=x, y=equity, name="Equity (inkl. floating)", mode="lines",
        line={"color": _FARBE_EQUITY, "width": 2.5},
        connectgaps=False,
        hovertemplate="%{x}<br>Equity %{y:,.0f} USD<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=realisiert, name="Realisiert (geschlossen)", mode="lines",
        line={"color": _FARBE_REALISIERT, "width": 1.6, "dash": "dot"},
        connectgaps=True,
        hovertemplate="%{x}<br>realisiert %{y:,.0f} USD<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=floating, name="Offener Betrag (floating)", mode="lines",
        line={"color": _FARBE_FLOATING, "width": 1.4},
        connectgaps=False,
        hovertemplate="%{x}<br>offen %{y:,.0f} USD<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=unterwasser, name="Unterwasser %", mode="lines",
        line={"color": _FARBE_FLOATING, "width": 1.2},
        fill="tozeroy", fillcolor="rgba(211,47,47,0.18)",
        connectgaps=False,
        hovertemplate="%{x}<br>%{y:.1f} % unter Hoch<extra></extra>"), row=2, col=1)

    if startkapital and startkapital > 0:
        fig.add_hline(y=startkapital, line_dash="dashdot", line_color="#9e9e9e",
                      line_width=1, annotation_text="Startkapital",
                      annotation_position="bottom right", row=1, col=1)

    # Maximaler Rückfall als Region mit Annotation.
    if k.get("dd_von") and k.get("dd_bis") and (k.get("equity_dd_usd") or 0) > 0:
        dd_text = (f"Max-Rückfall −{k['equity_dd_usd']:,.0f} USD"
                   + (f" ({k['dd_pct_am_usd_max']:.1f} %)" if k.get("dd_pct_am_usd_max")
                      is not None else ""))
        fig.add_vrect(
            x0=_als_datetime(k["dd_von"]), x1=_als_datetime(k["dd_bis"]),
            fillcolor="rgba(211,47,47,0.12)", line_width=0, row=1, col=1,
            annotation_text=dd_text, annotation_position="top left",
            annotation_font_color=_FARBE_FLOATING)

    fig.update_layout(
        height=560, margin={"l": 64, "r": 18, "t": 36, "b": 8},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        template="plotly_white",
    )
    fig.update_yaxes(title_text="USD", tickformat=",.0f", row=1, col=1,
                     gridcolor="#e8e8e8")
    fig.update_yaxes(title_text="%", row=2, col=1, gridcolor="#e8e8e8")
    fig.update_xaxes(rangeslider={"visible": True, "thickness": 0.075},
                     row=2, col=1)
    return fig


def _kennzahlen_karten(daten: dict, schranke: float) -> None:
    k = daten["kennzahlen"]
    pct = k.get("equity_dd_pct")
    with st.container(horizontal=True):
        st.metric(
            "Max-Drawdown (H1, virtuelle Equity)",
            f"{pct:.1f} %" if pct is not None else "—",
            "ohne Kapitalbasis" if pct is None else None,
            delta_color="off", border=True)
        st.metric("Rückfall (USD)",
                  f"−{k.get('equity_dd_usd', 0.0):,.0f}".replace(",", "."),
                  border=True)
        st.metric("Offener Betrag · tiefster",
                  f"{k.get('floating_min_usd', 0.0):,.0f} USD".replace(",", "."),
                  _als_datetime(k.get("floating_min_t")).strftime("%d.%m.%Y")
                  if k.get("floating_min_t") and k.get("floating_min_usd", 0) < 0
                  else None,
                  delta_color="off", border=True)
        st.metric("Unterwasser max",
                  f"{k.get('unterwasser_tage_max', 0.0):.0f} Tage",
                  border=True)
        st.metric("Abdeckung", f"{k.get('abdeckung_pct', 0.0):.0f} %", border=True)


def _konto_vergleich(daten: dict, key_prefix: str) -> None:
    """Tatsaechliches Kontokapital; Auszahlungen sind keine Trading-Verluste."""
    konto = daten.get("konto_studie") or {}
    if not konto.get("punkte"):
        if konto.get("grund"):
            st.warning("Konto-Diagnose nicht verfügbar: " + konto["grund"],
                       icon=":material/warning:")
        return
    k = konto.get("kennzahlen") or {}
    pct = k.get("konto_equity_dd_pct")
    if pct is None:
        pct = k.get("konto_equity_dd_beobachtet_pct")
    approximativ = not konto.get("verlaesslich")
    with st.container(border=True):
        st.markdown("**Konto-Equity mit tatsächlichen Kapitalflüssen**")
        st.metric("Konto-DD (H1, kapitalflussneutral)",
                  (("≈ " if approximativ else "") + f"{pct:.2f} %")
                  if pct is not None else "—", border=True)
        st.caption(
            "Ein- und Auszahlungen verändern das verfügbare Kapital. "
            "Der Renditeindex neutralisiert diese Buchungen, damit eine "
            "Auszahlung selbst keinen Handelsverlust erzeugt. Die blaue "
            "Konto-Kurve zeigt das tatsächliche Kapital einschließlich "
            "der Buchungen; die Drawdown-Spur misst den bereinigten Index.")
        if approximativ:
            st.warning(
                "Beobachteter H1-Wert, kein vollständiger Broker-Maximum-DD. "
                + (konto.get("grund") or "Kapital-/Kursbasis unvollständig."),
                icon=":material/warning:")
        if k.get("index_gueltig_bis") is not None:
            bis = _als_datetime(k["index_gueltig_bis"])
            st.caption(f"Gültige Index-Messpunkte bis {bis:%d.%m.%Y %H:%M} "
                       "in der Zeitbasis des Trade-Exports.")
        if k.get("index_abbruch_am") is not None:
            abbruch = _als_datetime(k["index_abbruch_am"])
            st.caption(f"Index ab {abbruch:%d.%m.%Y %H:%M:%S} nicht weiter "
                       "bestimmbar. Der angezeigte beobachtete Rückfall "
                       "gilt nur für die Messpunkte vor dem Abbruch.")
        st.caption(
            "Auch diese Kurve enthält ausschließlich die geschlossenen "
            "Exportpositionen. Die Gegenüberstellung verändert Ampel und "
            "Schranke nicht.")
        with st.expander("Konto-Kurve und kapitalflussneutraler Drawdown",
                         expanded=bool(k.get("flows_verarbeitet"))):
            punkte = konto["punkte"]
            x = [_als_datetime(p["t"]) for p in punkte]
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                row_heights=[0.7, 0.3], vertical_spacing=0.04)
            for feld, label, farbe in (
                    ("konto_equity", "Konto-Equity (inkl. Floating)", _FARBE_EQUITY),
                    ("konto_balance", "Kontobalance", _FARBE_REALISIERT)):
                fig.add_trace(go.Scatter(
                    x=x, y=[p[feld] for p in punkte], name=label,
                    mode="lines", line={"color": farbe}, connectgaps=False),
                    row=1, col=1)
            fig.add_trace(go.Scatter(
                x=x, y=[-p["drawdown_pct"] if p["drawdown_pct"] is not None else None
                        for p in punkte], name="Drawdown (Kapitalflüsse neutral)",
                mode="lines", line={"color": _FARBE_FLOATING}, connectgaps=False),
                row=2, col=1)
            fig.update_layout(height=460, hovermode="x unified", template="plotly_white",
                              margin={"l": 64, "r": 18, "t": 30, "b": 8},
                              legend={"orientation": "h", "y": 1.06})
            fig.update_yaxes(title_text="USD", row=1, col=1)
            fig.update_yaxes(title_text="%", row=2, col=1)
            st.plotly_chart(fig, width="stretch", config=_CHART_CONFIG,
                            key=f"{key_prefix}_konto_chart")


def _risiko_einschaetzung(result, daten: dict, schranke: float) -> None:
    """Text-Bausteine (Code, kein LLM): wie riskant zeigt sich die Strategie."""
    k = daten["kennzahlen"]
    pct = k.get("equity_dd_pct")
    vollstaendig = k.get("verlaesslich") is True
    if pct is None:
        st.info("Keine belastbare Kapitalbasis — Prozentwerte entfallen. Die "
                "USD-Verläufe zeigen die verfügbaren H1-Messpunkte.", icon=":material/info:")
    elif not vollstaendig:
        st.warning(f"**Unvollständige H1-Nachmessung:** {pct:.1f} % in den "
                   "verfügbaren Messpunkten. Fehlende Kurse oder ungeklärte "
                   "Zeitversätze verhindern eine belastbare Equity-Messung; "
                   "dieser Wert belegt kein Einhalten der Drawdown-Schranke.",
                   icon=":material/warning:")
    elif pct > schranke:
        st.error(f"**Drawdown-Schranke verletzt:** Die Nachmessung aus Kursen "
                 f"ergibt **{pct:.1f} %** maximalen Equity-Rückfall — über der "
                 f"harten Grenze von {schranke:.0f} %. Ein derartiger Rückfall "
                 f"ist aus Projektsicht nicht als Kandidat tragbar.",
                 icon=":material/report:")
    elif pct >= 0.8 * schranke:
        st.warning(f"**Kurz unter der Schranke:** {pct:.1f} % von "
                   f"{schranke:.0f} % Grenze — wenig Puffer; ein ungünstiger "
                   "Abschnitt kann die Strategie kippen lassen.",
                   icon=":material/warning:")
    else:
        st.info(f"**H1-Messwert unter der Schranke:** {pct:.1f} % "
                f"(Grenze {schranke:.0f} %). Verluste innerhalb einer Stunde "
                "und aktuell offene, im Export fehlende Positionen können "
                "den tatsächlichen Equity-Drawdown erhöhen.", icon=":material/info:")

    bausteine: list[str] = []
    dd_von, dd_bis = _als_datetime(k.get("dd_von")), _als_datetime(k.get("dd_bis"))
    if (k.get("equity_dd_usd") or 0) > 0:
        spanne = ""
        if dd_von and dd_bis:
            spanne = f" zwischen {dd_von:%d.%m.%Y} und {dd_bis:%d.%m.%Y}"
        bausteine.append(
            f"Größter rekonstruierter Rückfall: **−{k['equity_dd_usd']:,.0f} USD**"
            + (f" ({k['dd_pct_am_usd_max']:.1f} % vom damaligen Hoch)"
               if k.get("dd_pct_am_usd_max") is not None else "") + spanne + ".")
    if k.get("dd_rel_bis") and pct is not None:
        rel_von = _als_datetime(k.get("dd_rel_von"))
        rel_bis = _als_datetime(k["dd_rel_bis"])
        bausteine.append(
            f"Größter relativer Rückfall: **{pct:.2f} %** "
            f"(**−{k.get('dd_usd_am_rel_max', 0):,.0f} USD**)"
            + (f" zwischen {rel_von:%d.%m.%Y} und {rel_bis:%d.%m.%Y}"
               if rel_von else f" am {rel_bis:%d.%m.%Y}") + ".")
    if (k.get("floating_min_usd") or 0) < 0:
        wann = (f" (tiefstes am {dt.datetime.fromtimestamp(k['floating_min_t'], dt.timezone.utc):%d.%m.%Y})"
                if k.get("floating_min_t") else "")
        bausteine.append(
            f"Offene Positionen standen zeitweise **{k['floating_min_usd']:,.0f} USD "
            f"im Minus**{wann} — genau dieser unverwirklichte Betrag ist der "
            "Grund, warum der Max-Drawdown aus nur geschlossenen Trades die "
            "Belastung unterschätzen kann.")
    if (k.get("unterwasser_tage_max") or 0) > 0:
        bausteine.append(
            f"Längste Phase unter dem letzten Höchststand: "
            f"**{k['unterwasser_tage_max']:.0f} Tage** — so lange lag das Konto "
            "unter einem früheren Stand, ohne es wieder erreicht zu haben.")
    if getattr(result, "martingale_flag", False):
        bausteine.append("Martingale-Signatur erkannt (Lot-Erhöhung nach "
                         "Verlust) — Positionsgrößen wachsen genau in den "
                         "Verlustphasen.")
    if getattr(result, "peak_positionen", None):
        bausteine.append(f"Maximal **{result.peak_positionen} gleichzeitige "
                         "Positionen** in der Historie.")
    if bausteine:
        st.markdown("\n\n".join(f"• {b}" for b in bausteine))

    # Gegenüberstellung der Messungen: Plattform-Selbstauskunft, Monitor-
    # Zweitmessung und diese Nachmessung aus Kursen.
    gemeldet = getattr(result, "dd_equity_pct", None)
    monitor = getattr(result, "monitor_trade_eq_dd_pct", None)
    if pct is not None and gemeldet:
        if pct >= 1.5 * float(gemeldet):
            st.warning(f"**Nachmessung deutlich höher als der Plattformwert:** "
                       f"{pct:.1f} % hier vs. {float(gemeldet):.1f} % Drawdown "
                       f"(Plattform, Faktor {pct / float(gemeldet):.1f}×). "
                       "Abweichende DD-Definitionen, Kapitalflüsse, Zeiträume und Referenzkurse "
                       "müssen vor einer Aussage über die Meldung abgeglichen werden.",
                       icon=":material/compare_arrows:")
        else:
            st.caption(f"Vergleich: Drawdown (Plattform) "
                       f"{float(gemeldet):.1f} % · Max-Drawdown (Kurse) "
                       f"{pct:.1f} %.")
    if monitor is not None:
        st.caption(f"Monitor-Zweitmessung (volle Trade-Kurve): "
                   f"{float(monitor):.1f} % — unabhängige dritte Messung.")


def _symbol_diagnose(daten: dict) -> None:
    """GMT je Währungspaar, fehlende Kurse und Datenbasis offenlegen."""
    zeitbasis = daten.get("zeitbasis") or {}
    if zeitbasis:
        with st.expander(f"Zeitbasis der Kurve: {zeitbasis.get('modus', 'unbekannt')}"):
            if zeitbasis.get("angewandt") is False:
                st.caption("Dieses gemeinsame Zeitmodell wurde nicht auf die Kurve angewandt; "
                           "die Symbol-Zeitversätze sind uneinheitlich.")
            if zeitbasis.get("perioden"):
                st.dataframe(zeitbasis["perioden"], hide_index=True, width="stretch")
            if zeitbasis.get("annahme"):
                st.caption(zeitbasis["annahme"])
            if not zeitbasis.get("verlaesslich", False):
                st.warning("Zeitzuordnung nicht vollständig belegt: "
                           + " · ".join(zeitbasis.get("gruende") or ["Preisabgleich unklar"]))
    symbole = daten.get("symbole") or []
    if symbole:
        def gmt_text(b):
            modell = b.get("zeitbasis") or zeitbasis
            if modell.get("modus") == "wochenweise" and modell.get("angewandt") is not False:
                werte = sorted({p["gmt_h"] for p in modell.get("perioden", [])
                                if isinstance(p.get("gmt_h"), int)})
                return "abschnittsweise (" + ", ".join(f"{h:+d} h" for h in werte) + ")"
            return f"{b['gmt_h']:+d} h" if b.get("gmt_h") is not None else "—"

        def zeit_status(b):
            modell = b.get("zeitbasis") or zeitbasis
            if modell.get("angewandt") is False:
                return "⚠️ uneinheitliche Symbol-Zeitversätze"
            if modell.get("modus") == "wochenweise":
                return ("✅ abschnittsweise belegt" if modell.get("verlaesslich")
                        else "⚠️ Zeitbasis unvollständig")
            return {"erkannt": "✅ eigenständig erkannt",
                    "fallback_median": "↳ Fallback Median"}.get(
                b.get("status"), "⚠️ " + str(b.get("status")))

        zeilen = [{
            "Symbol": b["symbol"],
            "GMT": gmt_text(b),
            "Globaler Preisabgleich": (f"{b['trefferquote']:.0%}"
                              if b.get("trefferquote") is not None else "—"),
            "Status": zeit_status(b),
            "Hinweis": b.get("hinweis") or "",
        } for b in symbole]
        st.dataframe(zeilen, hide_index=True, width="stretch")
        for b in symbole:
            zeitbasis = b.get("zeitbasis") or {}
            if not zeitbasis:
                continue
            with st.expander(f"Zeitbasis {b['symbol']}: {zeitbasis.get('modus', 'unbekannt')}"):
                perioden = zeitbasis.get("perioden") or []
                if perioden:
                    st.dataframe(perioden, hide_index=True, width="stretch")
                if zeitbasis.get("annahme"):
                    st.caption(zeitbasis["annahme"])
                if not zeitbasis.get("verlaesslich", False):
                    st.warning("Zeitzuordnung nicht vollständig belegt: "
                               + " · ".join(zeitbasis.get("gruende") or ["Preisabgleich unklar"]))

    ohne_kurse = daten.get("symbole_ohne_kurse") or []
    ohne_kontrakt = daten.get("symbole_ohne_kontrakt") or []
    k = daten.get("kennzahlen") or {}
    if ohne_kurse or ohne_kontrakt or k.get("trades_genutzt", 0) < k.get("trades_total", 0):
        teile = []
        if ohne_kurse:
            teile.append("keine Kurse vom Referenzterminal: " + ", ".join(ohne_kurse))
        if ohne_kontrakt:
            teile.append("Kontraktgröße unbelegt: " + ", ".join(ohne_kontrakt))
        if k.get("trades_genutzt", 0) < k.get("trades_total", 0):
            teile.append(f"{k['trades_total'] - k.get('trades_genutzt', 0)} von "
                         f"{k['trades_total']} Trades ohne belegte Floating-Messung")
        st.warning("Realisierte Nettoergebnisse bleiben vollständig enthalten. "
                   "Fehlen Kurse, Kontraktgröße oder GMT-Versatz einer offenen "
                   "Position, ist die Equity dort eine Lücke. "
                   "**Der Drawdown kann dadurch unterschätzt werden.** Fehlt: " + " · ".join(teile),
                   icon=":material/warning:")
    if k.get("fx_luecke"):
        st.caption("EZB-Referenzkurs fehlte an einzelnen Tagen "
                   "(Fremdwährungs-Quotes) — diese Stunden sind Lücken in der "
                   "Equity-Spur.")
    if (k.get("punkte_mit_luecke") or 0) > 0:
        st.caption(f"{k['punkte_mit_luecke']} Stunden mit offenen Positionen "
                   "ohne vollständige Kurse — als Lücke in der Equity-Spur "
                   "gezeigt, nicht interpoliert.")


def render_studie(result, *, key_prefix: str = "eqdd") -> None:
    """Komplette Studiensicht: Progress beim Rechnen, danach Chart + Texte.

    Wird vom Dialog (Ergebnistabelle/Detail) und von der eigenen Seite
    equity_studie.py benutzt. Ergebnisse werden je (Signal-ID, Trade-SHA) in
    der Sitzung gecacht — der zweite Klick ist sofort da.
    """
    settings = config.load_settings()
    schranke = float(settings.get("schranke_eq_dd_pct", 30.0))
    meta_name = getattr(result, "name", "") or f"#{result.id}"
    ampel = getattr(result, "ampel", "")
    quelle = getattr(result, "quelle", "mql5") or "mql5"

    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**{ampel} {meta_name}** · #{result.id} · Quelle {quelle}")
        neu_klick = st.button("Neu berechnen", key=f"{key_prefix}_neu",
                              icon=":material/refresh:",
                              help="Wirft das Sitzungs-Cache weg und misst "
                                   "erneut (Terminal-Verbindung + Kurse werden "
                                   "frisch geladen).")

    cache_key = _cache_key(result)
    daten = None if neu_klick else st.session_state.get(cache_key)
    if daten is None:
        if scan_worker.active_run() is not None:
            st.info("Gerade läuft ein Scan — die Studie braucht das "
                    "MT5-Terminal exklusiv. Bitte warten, bis der Scan "
                    "fertig ist, dann erneut klicken.",
                    icon=":material/hourglass_top:")
            return
        bar = st.progress(0.0, text="Studie starten …")
        try:
            daten = berechne(result, lambda a, t: bar.progress(
                max(0.0, min(1.0, a)), text=t))
        except RuntimeError as exc:
            bar.empty()
            st.error(str(exc), icon=":material/error_outline:")
            return
        except Exception as exc:  # Unerwartetes soll den Dialog nicht ohne Diagnose schließen
            bar.empty()
            st.error(f"Studie fehlgeschlagen: {type(exc).__name__}: {exc}",
                     icon=":material/error_outline:")
            return
        bar.empty()
        st.session_state[cache_key] = daten
        st.toast("Equity-Studie berechnet", icon=":material/monitoring:")

    if daten.get("status") != "ok":
        st.warning(f"Studie nicht möglich: {daten.get('grund')}",
                   icon=":material/block:")
        _symbol_diagnose(daten)
        return

    k = daten["kennzahlen"]
    meta = daten.get("meta", {})
    _kennzahlen_karten(daten, schranke)

    basis_text = (f"{meta.get('startkapital_quelle', 'unbekannt')} · "
                  f"{k['startkapital']:,.0f} USD".replace(",", "."))
    zeitraum = ""
    if daten["punkte"]:
        erster = _als_datetime(daten["punkte"][0]["t"])
        letzter = _als_datetime(daten["punkte"][-1]["t"])
        zeitraum = f"{erster:%d.%m.%Y} – {letzter:%d.%m.%Y}"
    st.caption(
        f"{k.get('trades_realisiert', k['trades_total'])} Trades realisiert, "
        f"{k['trades_genutzt']} mit Kurs-/Kontrakt-/GMT-Basis · Zeitraum "
        f"{zeitraum} · Kapitalbasis: {basis_text} · {k['rasterpunkte']} "
        f"Stundenpunkte, davon {k['messpunkte']} mit offenen Positionen und "
        f"vollständigen Kursen · Abdeckung {k['abdeckung_pct']:.0f} %")
    st.caption(
        "Equity = Startkapital + realisiertes Netto + Summe des offenen PnL "
        "aller Positionen im Export. Die Kurve behält Gewinne rechnerisch "
        "im Konto; spätere Ein- und Auszahlungen sind nicht enthalten. "
        "Damit misst sie virtuelle Trading-Equity. Der tatsächliche "
        "Konto-Equity-DD hat bei Kontobewegungen eine andere Bezugsbasis.")
    st.caption(
        "Max-Drawdown dieser Kurve = Rückgang vom bisherigen Equity-Höchststand. "
        "Die öffentliche MQL-Drawdown-Grafik zeigt dagegen offenen Verlust / "
        "zeitgleiche Balance. Bei den drei am 03.10.2026 geprüften Signalen "
        "entsprach deren Maximum dem Wert ‚By Equity‘; dieser ist kein direkter "
        "Vergleichswert für den Höchststand-Drawdown. Das Listen-/Radar-Maximum "
        "nimmt den höheren Plattformwert aus Balance und Equity.")
    if k.get("trades_ohne_h1_floating_messpunkt"):
        st.caption(
            f"{k['trades_ohne_h1_floating_messpunkt']} Trades haben zwischen "
            "Öffnung und Schließung keinen H1-Schlusszeitpunkt. Ihr "
            "realisiertes Netto wird erfasst, ihr zwischenzeitlicher "
            "offener Verlust ist mit diesem Raster nicht messbar.")

    st.plotly_chart(_chart(daten, k.get("startkapital") or 0.0, schranke),
                    width="stretch", config=_CHART_CONFIG,
                    key=f"{key_prefix}_chart")
    _konto_vergleich(daten, key_prefix)

    with st.container(border=True):
        st.markdown("**Wie riskant zeigt sich die Strategie?** "
                    "(Messung aus Kursen, Bewertung bleibt bei der Engine)")
        _risiko_einschaetzung(result, daten, schranke)

    with st.container(border=True):
        st.markdown("**GMT-Abgleich je Währungspaar und Zeitabschnitt** — Trade-Zeiten sind "
                    "naive CSV-Zeiten ohne Zeitzonenbeleg, Kurszeiten "
                    "Epoch-Zeitstempel des Referenz-Terminals; der relative Versatz wird je Symbol per "
                    "Preisabgleich (Open/Close gegen die High-Low-Spanne der "
                    "H1-Bar) bestimmt. Ein wechselnder Versatz wird abschnittsweise "
                    "geprüft; unklare Abschnitte bleiben als Messgrenze sichtbar.")
        _symbol_diagnose(daten)

    st.caption("Messbasis: H1-Bars des Tickmill-Referenzterminals (Bar-Close), "
               "nicht die Broker-Kurse des Signals selbst. Zwischentick-"
               "Tiefs innerhalb einer Stunde können tiefer liegen als die "
               "stundenfeine Kurve zeigt. Handelsereignisse werden am "
               "ersten H1-Schluss nach ihrer tatsächlichen Zeit erfasst. "
               "Aktuell offene Positionen fehlen im Historien-Export. "
               "Spread sowie historische Gebühren während der Haltedauer "
               "sind aus H1-Kursen und Positions-CSV nicht vollständig messbar.")


@st.dialog("Equity-DD-Studie — aus Kursen nachgemessen", width="large")
def equity_studie_dialog(result) -> None:
    """Fenster von der Ergebnisstabelle/Detailansicht aus."""
    render_studie(result, key_prefix=f"eqdd_dialog_{result.id}")
