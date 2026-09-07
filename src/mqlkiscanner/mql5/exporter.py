# -*- coding: utf-8 -*-
"""Exporter: Trade-Export je Signal -> data/trades/{ID}.csv (Phase 1).

- Erfolgs-Check "Time;" liegt in session.export_positions_csv.
- Cache: existiert die Datei juenger als `cache_stunden`, wird NICHT
  erneut geladen (Rate-Limit-Schonung, ToS-Risiko).
"""
from __future__ import annotations

import csv
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from ..config import TRADES_DIR
from ..parser import load_export
from .session import Mql5Session


def publish_validated_export(source: Path, target: Path) -> None:
    """Only publish a structurally valid CSV; preserve any previous cache on failure.

    Both paths must be on the same filesystem for atomic replacement. Validation
    deliberately excludes forensic/strategy checks: a risky signal is valid data.
    """
    load_export(str(source))
    os.replace(source, target)


def export_positions(session: Mql5Session, signal_id: int,
                     cache_stunden: float = 24.0,
                     extra_pause_s: float = 0.0,
                     platform: str | None = None) -> tuple[str, bool]:
    """Laedt den Positions-/History-Export; Rueckgabe (pfad, aus_cache).

    platform steuert den Export-Pfad (MT4=history, MT5=positions).
    """
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    path = TRADES_DIR / f"{signal_id}_positions.csv"
    if path.exists():
        age_h = (time.time() - path.stat().st_mtime) / 3600.0
        if cache_stunden > 0 and age_h < cache_stunden:
            try:
                load_export(str(path))
            except (ValueError, csv.Error):
                # A malformed download must not poison all retries for 24 hours.
                path.unlink()
            else:
                return str(path), True
    text = session.export_positions_csv(
        signal_id, extra_pause_s=extra_pause_s, platform=platform)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=TRADES_DIR,
                                         suffix=".csv", delete=False) as fh:
            temporary = Path(fh.name)
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        publish_validated_export(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
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
