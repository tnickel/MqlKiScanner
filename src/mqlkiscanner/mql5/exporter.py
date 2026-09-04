# -*- coding: utf-8 -*-
"""Exporter: Trade-Export je Signal -> data/trades/{ID}.csv (Phase 1).

- Erfolgs-Check "Time;" liegt in session.export_positions_csv.
- Cache: existiert die Datei juenger als `cache_stunden`, wird NICHT
  erneut geladen (Rate-Limit-Schonung, ToS-Risiko).
"""
from __future__ import annotations

import time
from datetime import datetime

from ..config import TRADES_DIR
from .session import Mql5Session


def export_positions(session: Mql5Session, signal_id: int,
                     cache_stunden: float = 24.0,
                     extra_pause_s: float = 0.0) -> tuple[str, bool]:
    """Laedt den Positions-Export; Rueckgabe (pfad, aus_cache)."""
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    path = TRADES_DIR / f"{signal_id}_positions.csv"
    if path.exists():
        age_h = (time.time() - path.stat().st_mtime) / 3600.0
        if age_h < cache_stunden:
            return str(path), True
    text = session.export_positions_csv(signal_id, extra_pause_s=extra_pause_s)
    path.write_text(text, encoding="utf-8")
    return str(path), False


def cache_info(signal_id: int) -> dict:
    path = TRADES_DIR / f"{signal_id}_positions.csv"
    if not path.exists():
        return {"vorhanden": False}
    return {
        "vorhanden": True,
        "pfad": str(path),
        "alter_stunden": round((time.time() - path.stat().st_mtime) / 3600.0, 1),
        "geladen_am": datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" "),
    }
