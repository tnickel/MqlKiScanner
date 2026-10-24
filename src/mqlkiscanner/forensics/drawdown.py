# -*- coding: utf-8 -*-
"""Forensik-Test 4: Drawdown-Rekonstruktion + Konsistenz (doc/03).

Kurven (Regel 05.10.2026 — Nutzer-Entscheid „Einzahlungen drin lassen"):
- KONTO-Kurve ("trading_dd", HAUPTWERT): reale Kontokurve inkl. aller
  Ein-/Auszahlungen. Einzahlungen heben Kurve und Peak — der Betreiber
  erhöht danach seine Lots, also wachsen spätere Drawdowns in USD und %,
  genau wie es ein Kopierer erlebt. AUSZAHLUNGEN erzeugen KEINEN
  Drawdown: der laufende Peak wird um den Auszahlungsbetrag gesenkt
  (nie unter den aktuellen Stand; Hochwassermark-Methode mit
  Flow-Anpassung) — Geld, das das Konto verlässt, ist kein Verlust.
  Ohne Balance-Zeilen im Export bleibt zwangsläufig die virtuelle Kurve
  (klar markiert im Feld „kurve"), dann gilt: nichts erfinden.
- Virtuelle Kurve ("trading_dd_virtuell", Diagnostik): Startkapital +
  Netto der Trades OHNE spätere Kontobewegungen — alte Hauptkurve,
  bleibt für den kapitalflussneutralen Vergleich.

Pro Trade zaehlt das NETTO (Profit + Kommission + Swap).
"""
from __future__ import annotations

import math
from itertools import groupby

from ..models import ParsedExport
from .drawdown_core import max_drawdown_aus_kurve


def unterwasser_verlauf(staende: list, fluesse: list) -> list:
    """Unterwasser-% je Punkt (≤ 0) nach derselben Peak-Regel wie die DD-Engine.

    staende: Kontostand je Punkt (None = kein Messpunkt, bleibt None);
    fluesse: Ein-/Auszahlung, die an diesem Punkt gebucht wurde. Auszahlungen
    senken den Peak (nie unter den Stand) — Geld, das das Konto verlässt, ist
    kein Drawdown (Nutzer-Regel 05.10.2026). Flüsse an Nicht-Messpunkten
    werden bis zum nächsten Messpunkt mitgeführt, nicht verworfen.
    """
    result = max_drawdown_aus_kurve(
        ((index, wert, wert is not None, fluss)
         for index, (wert, fluss) in enumerate(zip(staende, fluesse))), verlauf=True)
    return [punkt["unterwasser_pct"] if punkt is not None else None
            for punkt in result["verlauf"]]


def floating_dd_verlauf(balancen: list, floatings: list) -> list:
    """Equity-Drawdown wie die MQL5-Signalseite (≤ 0 %): offener Verlust im
    Verhältnis zur aktuellen Balance, (Equity − Balance) / Balance.

    Nutzer-Fall KiraCat 05.10.2026: Die MQL5-Grafik fällt ohne offene
    Position immer auf 0 (282 Nullwerte bei 310 flachen Zeitpunkten) —
    realisierte Verluste und Auszahlungen gehen dort nicht ein. floating
    None = kein Messpunkt (bleibt None).
    """
    verlauf: list = []
    for balance, floating in zip(balancen, floatings):
        if floating is None or balance is None:
            verlauf.append(None)
        elif floating >= 0 or balance <= 0:
            verlauf.append(0.0)
        else:
            verlauf.append(floating / balance * 100.0)
    return verlauf


def _max_drawdown(points: list[tuple], start: float) -> dict:
    """points: chronologische (zeitpunkt, delta)-Ereignisse.

    dd_usd / dd_pct: groesster *Dollar*-Rueckgang und %-Wert an genau diesem
    Ereignis (Cent-Anker / verify_engine). dd_pct_max_rel: Maximum aller
    relativen Rueckgaenge — fuer Risiko-Score und Schranke.
    """
    bal = float(start)
    curve = []
    # CSV timestamps do not establish an order inside a second. Book each
    # timestamp together rather than manufacture row-order-dependent peaks.
    for time, batch in groupby(sorted(points, key=lambda p: p[0]), key=lambda p: p[0]):
        bal += math.fsum(point[1] for point in batch)
        curve.append((time, bal, True, 0.0))
    return _closing_result(max_drawdown_aus_kurve(
        curve, start=start, nichtpositiver_peak_pct=100.0))


def _closing_result(result: dict) -> dict:
    """The legacy closing schema, formatted once at the output boundary."""
    when, when_rel = result["dd_time"], result["dd_time_max_rel"]
    return {
        "dd_usd": round(result["dd_usd_raw"], 2),
        "dd_usd_raw": result["dd_usd_raw"],
        "dd_pct": round(result["dd_pct_raw"], 2),
        "dd_pct_max_rel": round(result["dd_pct_max_rel_raw"], 2),
        "dd_pct_raw": result["dd_pct_raw"],
        "dd_pct_max_rel_raw": result["dd_pct_max_rel_raw"],
        "dd_date": when.date().isoformat() if when else None,
        "dd_date_max_rel": when_rel.date().isoformat() if when_rel else None,
        "end_balance": round(result["end_balance_raw"], 2),
        "peak_balance": round(result["peak_balance_raw"], 2),
    }


def _konto_ereignisse(parsed, erster_open=None) -> tuple[list, list]:
    """Net results from first open and later external flows, each once."""
    if erster_open is None:
        erster_open = min((t.open_time for t in parsed.trades), default=None)
    if erster_open is None:
        return [], []
    trading = [(t.close_time, t.net) for t in parsed.trades] + [
        (c.time, c.amount) for c in getattr(parsed, "costs", []) if c.time >= erster_open]
    flows = [(b.time, b.amount) for b in getattr(parsed, "balances", []) if b.time > erster_open]
    return trading, flows


def konto_drawdown(parsed, startkapital: float) -> dict:
    """Closing DD with a resolved start balance, including later known flows.

    The supplied balance already includes pre-start flows and pre-start costs.
    Percentage outputs use percent units; ``dd_pct_max_rel_raw`` is unrounded.
    This adapter does not resolve capital again or modify the export.
    """
    trading, flows = _konto_ereignisse(parsed)
    return (_max_drawdown_konto(trading, flows, startkapital) if flows else
            _max_drawdown(trading, startkapital))


def run(parsed: ParsedExport, kapitalbasis_usd: float | None = None,
        kapitalbasis_quelle: str | None = None, *, kapital_kontext: dict | None = None,
        quellen_stats: dict | None = None, kapitalentscheidung: dict | None = None,
        broker: str | None = None) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "drawdown"}
    balances = sorted(parsed.balances, key=lambda b: b.time)
    first_open = min(t.open_time for t in trades)

    # Bereits vor Handelsbeginn entnommenes Kapital stand nie fuer Trades
    # bereit. Nur spaetere Flows bleiben aus der virtuellen Kurve heraus.
    deposits_start = math.fsum(b.amount for b in balances if b.time <= first_open)
    from .. import kapitalbasis
    decision = kapitalentscheidung if kapitalentscheidung is not None else kapitalbasis.aufloesen(
        parsed, stats=quellen_stats, kapitalbasis_usd=kapitalbasis_usd,
        kapitalbasis_quelle=kapitalbasis_quelle, broker=broker, kontext=kapital_kontext)
    injected = float(decision["injektion_usd"])
    startkapital_quelle = decision["quelle"]
    if not math.isfinite(injected) or not math.isclose(
            deposits_start + injected, float(decision["kapital"]), rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("Kapitalentscheidung passt nicht zu den Vorstartbuchungen des Exports.")
    kosten_vor_start = math.fsum(c.amount for c in getattr(parsed, "costs", []) if c.time < first_open)
    startkapital = deposits_start + injected + kosten_vor_start
    deposits_total = sum(b.amount for b in balances if b.amount > 0)
    withdrawals_total = sum(b.amount for b in balances if b.amount < 0)

    # Nur Kosten VOR dem ersten Open stecken bereits im Startsaldo.
    trading_points, flows_nach_start = _konto_ereignisse(parsed, first_open)
    trading_virtuell = _max_drawdown(trading_points, startkapital)

    # Balance-Kurve: CSV-Buchungen buchen sich selbst; die injizierte Basis
    # ist keine Zeile und geht deshalb als Startwert ein.
    balance_points = [(b.time, b.amount) for b in balances] + parsed.realized_events()
    balance_points.sort(key=lambda p: p[0])
    balance = _max_drawdown(balance_points, injected)

    # KONTO-Kurve (HAUPTWERT, Nutzer-Regel 05.10.2026): Trades PLUS Flows
    # nach Handelsbeginn. Einzahlungen heben den Peak, Auszahlungen senken
    # ihn um ihren Betrag — Auszahlungen erzeugen keinen Drawdown.
    if flows_nach_start:
        trading = _max_drawdown_konto(trading_points, flows_nach_start, startkapital)
        kurve = "real_mit_flows"
    else:
        trading = trading_virtuell
        kurve = "virtuell_ohne_flows"

    flows_total = deposits_total + withdrawals_total
    net_total = parsed.net_total
    return {
        "test": "drawdown",
        "start_capital": round(deposits_start, 2),
        "startkapital": round(startkapital, 2),
        "startkapital_raw": startkapital,
        "startkapital_quelle": startkapital_quelle,
        "kapitalbasis_details": decision,
        "kapitalbasis_modell": bool(decision.get("modell")),
        "kontokosten_vor_start_usd": kosten_vor_start,
        "kontokosten_usd": math.fsum(c.amount for c in getattr(parsed, "costs", [])),
        "deposits_total": round(deposits_total, 2),
        "withdrawals_total": round(withdrawals_total, 2),
        "flows_total": round(flows_total, 2),
        "net_total": round(net_total, 2),
        # flows_total enthaelt deposits_start bereits (alle positiven Balance-Zeilen).
        "end_balance_estimated": round(flows_total + net_total, 2),
        # Tatsaechlicher Kontostand am CSV-Ende inkl. injizierter Basis —
        # Anker fuer den Abgleich mit dem Webseiten-Kontostand.
        "end_balance_real": round(flows_total + net_total + injected, 2),
        "kurve": kurve,
        "trading_dd": trading,      # HAUPTWERT: reale Kontokurve (Nutzer-Regel 05.10.)
        "trading_dd_virtuell": trading_virtuell,  # Diagnostik: ohne Flows (alt)
        "balance_dd": balance,      # Diagnostik (Auszahlungs-Artefakte moeglich)
    }


def _max_drawdown_konto(trade_points: list[tuple], flow_points: list[tuple],
                        start: float) -> dict:
    """Drawdown auf der REALEN Kontokurve inkl. Ein-/Auszahlungen.

    trade_points: (close_time, netto) der Trades; flow_points: (zeit,
    betrag) der Kontobewegungen NACH Handelsbeginn. Beide werden
    chronologisch gebucht; Zeitstempel-Gleicheit bucht gemeinsam (wie
    _max_drawdown). Auszahlungen (negativer Flow) senken den bisherigen
    Peak um ihren Betrag — nie unter den aktuellen Stand — damit Geld,
    das das Konto verlaesst, keinen Drawdown erzeugt (Nutzer-Regel
    05.10.2026: „wenn er mehr einzahlt, geht die Lotsize hoch und der
    Drawdown wächst; Auszahlungen sind keine Verluste").
    """
    from collections import defaultdict
    je_zeitpunkt: dict = defaultdict(lambda: [0.0, 0.0])  # zeit -> [trade, flow]
    for zeit, delta in trade_points:
        je_zeitpunkt[zeit][0] += delta
    for zeit, betrag in flow_points:
        je_zeitpunkt[zeit][1] += betrag

    bal = float(start)
    curve = []
    for zeit in sorted(je_zeitpunkt):
        trade_delta, flow_delta = je_zeitpunkt[zeit]
        bal += trade_delta + flow_delta
        curve.append((zeit, bal, True, flow_delta))
    return _closing_result(max_drawdown_aus_kurve(
        curve, start=start, nichtpositiver_peak_pct=100.0))
