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


def unterwasser_verlauf(staende: list, fluesse: list) -> list:
    """Unterwasser-% je Punkt (≤ 0) nach derselben Peak-Regel wie die DD-Engine.

    staende: Kontostand je Punkt (None = kein Messpunkt, bleibt None);
    fluesse: Ein-/Auszahlung, die an diesem Punkt gebucht wurde. Auszahlungen
    senken den Peak (nie unter den Stand) — Geld, das das Konto verlässt, ist
    kein Drawdown (Nutzer-Regel 05.10.2026). Flüsse an Nicht-Messpunkten
    werden bis zum nächsten Messpunkt mitgeführt, nicht verworfen.
    """
    hoch = None
    offen = 0.0
    verlauf: list = []
    for wert, fluss in zip(staende, fluesse):
        offen += fluss or 0.0
        if wert is None:
            verlauf.append(None)
            continue
        if offen < 0 and hoch is not None:
            hoch = max(wert, hoch + offen)
        offen = 0.0
        if hoch is None or wert > hoch:
            hoch = wert
        verlauf.append((wert / hoch - 1.0) * 100.0 if hoch > 0 else 0.0)
    return verlauf


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
    # CSV timestamps do not establish an order inside a second. Book each
    # timestamp together rather than manufacture row-order-dependent peaks.
    for _time, batch in groupby(sorted(points, key=lambda p: p[0]), key=lambda p: p[0]):
        delta = math.fsum(point[1] for point in batch)
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


def run(parsed: ParsedExport, kapitalbasis_usd: float | None = None,
        kapitalbasis_quelle: str | None = None) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "drawdown"}
    balances = sorted(parsed.balances, key=lambda b: b.time)
    first_open = min(t.open_time for t in trades)

    # Bereits vor Handelsbeginn entnommenes Kapital stand nie fuer Trades
    # bereit. Nur spaetere Flows bleiben aus der virtuellen Kurve heraus.
    deposits_start = math.fsum(b.amount for b in balances if b.time <= first_open)
    # Externe Kapitalbasis (Signalseite "Initial Deposit"): greift NUR, wenn
    # der Export selbst keine Einzahlung vor dem ersten Trade enthaelt
    # (MT4-Orderbuch beginnt mit der Signalhistorie). Die Webseite belegt
    # das Startkapital des Signal-Kontos unabhaengig davon.
    # Dieselbe Bedingung wie in forensics/exposure.py (F1, Review T1/2
    # 29.09.): frueher reichte hier netto <= 0 — Einzahlung +100/Auszahlung
    # -200 vor dem ersten Trade injizierte NUR im Drawdown, Exposure rechnete
    # mit -100: derselbe Report mit zwei verschiedenen Startkapitalen.
    hat_einzahlung_vor_start = any(
        b.amount > 0 and b.time <= first_open for b in balances)
    injected = 0.0
    startkapital_quelle = "csv_einzahlungen"
    if (not hat_einzahlung_vor_start and kapitalbasis_usd is not None
            and kapitalbasis_usd > 0):
        injected = float(kapitalbasis_usd)
        startkapital_quelle = kapitalbasis_quelle or "extern"
    startkapital = deposits_start + injected
    deposits_total = sum(b.amount for b in balances if b.amount > 0)
    withdrawals_total = sum(b.amount for b in balances if b.amount < 0)

    trading_points = [(t.close_time, t.net) for t in sorted(trades, key=lambda t: t.close_time)]
    trading_virtuell = _max_drawdown(trading_points, startkapital)

    # Balance-Kurve: CSV-Buchungen buchen sich selbst; die injizierte Basis
    # ist keine Zeile und geht deshalb als Startwert ein.
    balance_points = [(b.time, b.amount) for b in balances] + trading_points
    balance_points.sort(key=lambda p: p[0])
    balance = _max_drawdown(balance_points, injected)

    # KONTO-Kurve (HAUPTWERT, Nutzer-Regel 05.10.2026): Trades PLUS Flows
    # nach Handelsbeginn. Einzahlungen heben den Peak, Auszahlungen senken
    # ihn um ihren Betrag — Auszahlungen erzeugen keinen Drawdown.
    flows_nach_start = [(b.time, b.amount) for b in balances if b.time > first_open]
    if flows_nach_start:
        trading = _max_drawdown_konto(trading_points, flows_nach_start, startkapital)
        kurve = "real_mit_flows"
    else:
        trading = trading_virtuell
        kurve = "virtuell_ohne_flows"

    flows_total = deposits_total + withdrawals_total
    net_total = sum(t.net for t in trades)
    return {
        "test": "drawdown",
        "start_capital": round(deposits_start, 2),
        "startkapital": round(startkapital, 2),
        "startkapital_quelle": startkapital_quelle,
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

    bal = peak = float(start)
    max_dd = max_dd_pct = 0.0
    max_rel = 0.0
    when = when_rel = None
    for zeit in sorted(je_zeitpunkt):
        trade_delta, flow_delta = je_zeitpunkt[zeit]
        bal += trade_delta + flow_delta
        # Auszahlung: Peak mitigieren, BEVOR der Rueckgang gezaehlt wird.
        if flow_delta < 0:
            peak = max(bal, peak + flow_delta)
        if bal > peak:
            peak = bal
        dd = peak - bal
        if peak > 0:
            rel = dd / peak * 100
        elif dd > 0:
            rel = 100.0
        else:
            rel = 0.0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = rel
            when = zeit
        if rel > max_rel:
            max_rel = rel
            when_rel = zeit
    return {
        "dd_usd": round(max_dd, 2),
        "dd_pct": round(max_dd_pct, 2),
        "dd_pct_max_rel": round(max_rel, 2),
        "dd_date": when.date().isoformat() if when else None,
        "dd_date_max_rel": when_rel.date().isoformat() if when_rel else None,
        "end_balance": round(bal, 2),
        "peak_balance": round(peak, 2),
    }

