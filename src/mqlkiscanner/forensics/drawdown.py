# -*- coding: utf-8 -*-
"""Forensik-Test 4: Drawdown-Rekonstruktion + Konsistenz (doc/03).

Zwei Kurven (Spec doc/03_forensik-tests.md):
- Trading-Kurve ("virtuell"): Startkapital = Einzahlungen vor dem ersten
  Trade, KEINE weiteren Kontobewegungen — zeigt die Handelsleistung
  getrennt von der Kapitalentnahme. ANKER: an diesem DD haengt der
  Plattform-Abgleich auf den Cent (Reihe: MSC 76,83 / Reaper 319,49 /
  Gold Spike 157,20 / KiraCat 2.117,70 USD — exakt).
- Balance-Kurve: alle Balance-Zeilen an ihren Zeitpunkten eingerechnet.
  Auszahlungen erzeugen hier Schein-Drawdowns — nur Diagnostik.

Pro Trade zaehlt das NETTO (Profit + Kommission + Swap). Achtung: die
Referenzskripte addierten teils nur `profit` — mit Netto decken sich
alle vier Ankerwerte der Reihe auf den Cent (siehe scripts/verify_engine.py).
"""
from __future__ import annotations

from ..models import ParsedExport


def _max_drawdown(points: list[tuple], start: float) -> dict:
    """points: chronologische (zeitpunkt, delta)-Ereignisse.

    dd_usd / dd_pct: groesster *Dollar*-Rueckgang und %-Wert an genau diesem
    Ereignis (Cent-Anker / verify_engine). dd_pct_max_rel: Maximum aller
    relativen Rueckgaenge — fuer Risiko-Score und Schranke.
    """
    bal = peak = float(start)
    max_dd = max_dd_pct = 0.0
    max_rel = 0.0
    when = when_rel = None
    for _time, delta in points:
        bal += delta
        if bal > peak:
            peak = bal
        dd = peak - bal
        if peak > 0:
            rel = dd / peak * 100
        elif dd > 0:
            # Kein positives Peak-Kapital (fehlende Einzahlung) — Verlust trotzdem
            # als 100 % relativ werten, damit Score/Schranke nicht blind bleiben.
            rel = 100.0
        else:
            rel = 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = rel
            when = _time
        if rel > max_rel:
            max_rel = rel
            when_rel = _time
    return {
        "dd_usd": round(max_dd, 2),
        "dd_pct": round(max_dd_pct, 2),
        "dd_pct_max_rel": round(max_rel, 2),
        "dd_date": when.date().isoformat() if when else None,
        "dd_date_max_rel": when_rel.date().isoformat() if when_rel else None,
        "end_balance": round(bal, 2),
        "peak_balance": round(peak, 2),
    }


def run(parsed: ParsedExport) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "drawdown"}
    balances = sorted(parsed.balances, key=lambda b: b.time)
    first_open = min(t.open_time for t in trades)

    deposits_start = sum(b.amount for b in balances if b.amount > 0 and b.time <= first_open)
    deposits_total = sum(b.amount for b in balances if b.amount > 0)
    withdrawals_total = sum(b.amount for b in balances if b.amount < 0)

    trading_points = [(t.close_time, t.net) for t in sorted(trades, key=lambda t: t.close_time)]
    trading = _max_drawdown(trading_points, deposits_start)

    balance_points = [(b.time, b.amount) for b in balances] + trading_points
    balance_points.sort(key=lambda p: p[0])
    balance = _max_drawdown(balance_points, 0.0)

    flows_total = deposits_total + withdrawals_total
    net_total = sum(t.net for t in trades)
    return {
        "test": "drawdown",
        "start_capital": round(deposits_start, 2),
        "deposits_total": round(deposits_total, 2),
        "withdrawals_total": round(withdrawals_total, 2),
        "flows_total": round(flows_total, 2),
        "net_total": round(net_total, 2),
        # flows_total enthaelt deposits_start bereits (alle positiven Balance-Zeilen).
        "end_balance_estimated": round(flows_total + net_total, 2),
        "trading_dd": trading,      # ANKER fuer Plattform-Abgleich
        "balance_dd": balance,      # Diagnostik (Auszahlungs-Artefakte moeglich)
    }


def consistency_usd_dd(parsed: ParsedExport) -> float:
    """Der ankerrelevante Trading-DD in USD (Vergleich Plattform 'By Balance')."""
    return run(parsed)["trading_dd"]["dd_usd"]
