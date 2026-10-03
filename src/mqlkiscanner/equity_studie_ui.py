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
    return f"eqdd_studie_{result.id}_{sha[:12] or 'nosha'}"


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
        subplot_titles=("Kontostand: realisiert (geschlossen) · Equity (inkl. offener Positionen)",
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
                   + (f" ({k['equity_dd_pct']:.1f} %)" if k.get("equity_dd_pct")
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
            "Reko-EQ-DD max",
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


def _risiko_einschaetzung(result, daten: dict, schranke: float) -> None:
    """Text-Bausteine (Code, kein LLM): wie riskant zeigt sich die Strategie."""
    k = daten["kennzahlen"]
    pct = k.get("equity_dd_pct")
    if pct is None:
        st.info("Keine belastbare Kapitalbasis — Prozentwerte entfallen. Die "
                "USD-Verläufe (realisiert und offener Betrag) sind trotzdem "
                "exakt gemessen.", icon=":material/info:")
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
        st.success(f"**Im Rahmen:** {pct:.1f} % maximaler Equity-Rückfall "
                   f"(Grenze {schranke:.0f} %).", icon=":material/check_circle:")

    bausteine: list[str] = []
    dd_von, dd_bis = _als_datetime(k.get("dd_von")), _als_datetime(k.get("dd_bis"))
    if (k.get("equity_dd_usd") or 0) > 0:
        spanne = ""
        if dd_von and dd_bis:
            spanne = f" zwischen {dd_von:%d.%m.%Y} und {dd_bis:%d.%m.%Y}"
        bausteine.append(
            f"Größter rekonstruierter Rückfall: **−{k['equity_dd_usd']:,.0f} USD**"
            + (f" ({k['equity_dd_pct']:.1f} % vom damaligen Hoch)"
               if pct is not None else "") + spanne + ".")
    if (k.get("floating_min_usd") or 0) < 0:
        wann = (f" (tiefstes am {dt.datetime.fromtimestamp(k['floating_min_t'], dt.timezone.utc):%d.%m.%Y})"
                if k.get("floating_min_t") else "")
        bausteine.append(
            f"Offene Positionen standen zeitweise **{k['floating_min_usd']:,.0f} USD "
            f"im Minus**{wann} — genau dieser unverwirklichte Betrag ist der "
            "Grund, warum der reine Trading-DD (nur geschlossene Trades) die "
            "Belastung unterschätzt.")
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
            st.warning(f"**Nachmessung deutlich höher als gemeldet:** "
                       f"{pct:.1f} % hier vs. {float(gemeldet):.1f} % Plattform "
                       f"(Faktor {pct / float(gemeldet):.1f}×) — der Drawdown "
                       "war schöner gemeldet, als er war.",
                       icon=":material/compare_arrows:")
        else:
            st.caption(f"Vergleich: Plattform meldet {float(gemeldet):.1f} % "
                       f"EQ-DD · Nachmessung {pct:.1f} %.")
    if monitor is not None:
        st.caption(f"Monitor-Zweitmessung (volle Trade-Kurve): "
                   f"{float(monitor):.1f} % — unabhängige dritte Messung.")


def _symbol_diagnose(daten: dict) -> None:
    """GMT je Währungspaar, fehlende Kurse und Datenbasis offenlegen."""
    symbole = daten.get("symbole") or []
    if symbole:
        zeilen = [{
            "Symbol": b["symbol"],
            "GMT": f"{b['gmt_h']:+d} h" if b.get("gmt_h") is not None else "—",
            "Preisabgleich": (f"{b['trefferquote']:.0%}"
                              if b.get("trefferquote") is not None else "—"),
            "Status": {"erkannt": "✅ eigenständig erkannt",
                       "fallback_median": "↳ Fallback Median"}.get(
                b.get("status"), "⚠️ " + str(b.get("status"))),
            "Hinweis": b.get("hinweis") or "",
        } for b in symbole]
        st.dataframe(zeilen, hide_index=True, width="stretch")

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
                         f"{k['trades_total']} Trades ausgeschlossen")
        st.warning("Gerechnet wurde nur mit den Währungspaaren, für die Kurse "
                   "und Kontraktgröße vorliegen — **der Drawdown kann ohne die "
                   "fehlenden Symbole NIEDRIGER ausgefallen sein, als er "
                   "wirklich war.** Fehlt: " + " · ".join(teile),
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
        f"{k['trades_genutzt']} von {k['trades_total']} Trades · Zeitraum "
        f"{zeitraum} · Kapitalbasis: {basis_text} · {k['rasterpunkte']} "
        f"Stundenpunkte, davon {k['messpunkte']} mit offenen Positionen und "
        f"vollständigen Kursen · Abdeckung {k['abdeckung_pct']:.0f} %")

    st.plotly_chart(_chart(daten, k.get("startkapital") or 0.0, schranke),
                    width="stretch", config=_CHART_CONFIG,
                    key=f"{key_prefix}_chart")

    with st.container(border=True):
        st.markdown("**Wie riskant zeigt sich die Strategie?** "
                    "(Messung aus Kursen, Bewertung bleibt bei der Engine)")
        _risiko_einschaetzung(result, daten, schranke)

    with st.container(border=True):
        st.markdown("**GMT-Abgleich je Währungspaar** — Trade-Zeiten sind "
                    "Serverzeit des Signal-Brokers, Kurse Serverzeit des "
                    "Referenz-Terminals; der Versatz wird je Symbol per "
                    "Preisabgleich (Open/Close gegen die High-Low-Spanne der "
                    "H1-Bar) bestimmt.")
        _symbol_diagnose(daten)

    st.caption("Messbasis: H1-Bars des Tickmill-Referenzterminals (Bar-Close), "
               "nicht die Broker-Kurse des Signals selbst. Zwischentick-"
               "Tiefs innerhalb einer Stunde können tiefer liegen als die "
               "stundenfeine Kurve zeigt. Realisierte Gewinne werden zur "
               "Schluss-Stunde gebucht; der offene Betrag läuft mit jedem "
               "Stunden-Close mit.")


@st.dialog("Equity-DD-Studie — aus Kursen nachgemessen", width="large")
def equity_studie_dialog(result) -> None:
    """Fenster von der Ergebnisstabelle/Detailansicht aus."""
    render_studie(result, key_prefix=f"eqdd_dialog_{result.id}")
