# -*- coding: utf-8 -*-
"""News-Korrelation: FOMC-Entscheidungstage vs. Handeltage (doc/03, Soll).

Frage: Hat das System einen Nachrichtenfilter? Nachweisbar, wenn an
FOMC-Tagen signifikant weniger / keine Trades stattfinden.
Referenz: scripts/reference/news_check.py (FOMC-Liste 2024-2026).
"""
from __future__ import annotations

from collections import defaultdict

from ..models import ParsedExport

# FOMC-Entscheidungstage 2024-2026 (US-Ost; Entscheidung 14:00 ET)
# Quelle: Federal Reserve calendar — nach 2026-12 pflegen / warnen.
FOMC_DAYS: tuple[str, ...] = (
    "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07",
    "2024-12-18", "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10", "2026-01-28",
    "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
    "2026-10-28", "2026-12-09",
)


def run(parsed: ParsedExport, fomc_days: tuple[str, ...] = FOMC_DAYS) -> dict:
    by_day: dict[str, int] = defaultdict(int)
    for t in parsed.trades:
        by_day[t.open_time.date().isoformat()] += 1

    if not by_day:
        return {"test": "news", "fomc_days_in_period": 0}

    first, last = min(by_day), max(by_day)
    relevant = [d for d in fomc_days if first <= d <= last]
    quiet = [d for d in relevant if by_day.get(d, 0) == 0]
    list_end = max(fomc_days) if fomc_days else ""
    overdue = bool(list_end and last > list_end)
    return {
        "test": "news",
        "period_from": first,
        "period_to": last,
        "fomc_days_in_period": len(relevant),
        "fomc_days_without_trades": len(quiet),
        "fomc_quiet_pct": round(len(quiet) / len(relevant) * 100, 0) if relevant else None,
        "fomc_days_detail": {d: by_day.get(d, 0) for d in relevant},
        "active_trading_days": len(by_day),
        "fomc_calendar_stale": overdue,
        "filter_hint": (
            "FOMC-Kalender endet vor dem Trade-Zeitraum — Liste aktualisieren"
            if overdue else
            ("Nachrichtenfilter wahrscheinlich (FOMC-Tag meistenteils ausgespart)"
             if relevant and len(quiet) / len(relevant) >= 0.7
             else "kein ausgepraegter FOMC-Filter erkennbar")
        ),
    }
