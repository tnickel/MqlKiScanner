# -*- coding: utf-8 -*-
"""Parser fuer MQL5-Trade-Exporte.

Zwei CSV-Varianten (doc/02_technik-mql5.md Abschnitt 3):
- Positions-Export (11 Spalten, Profit = Idx 10, Close = Idx 6/7)
- MT4-Orderbuch (13 Spalten, S/L = Idx 5, T/P = Idx 6, Profit = Idx 11,
  Kommentar = Idx 12)

Fallstricke, die hier behandelt werden:
- Tausendertrennzeichen als Leerzeichen bzw. NBSP ("1 403.03")
- Zeilen, die kuerzer als die Kopfzeile sind, werden uebersprungen
- Balance-Zeilen: Betrag steht in der Profit-Spalte des jeweiligen Formats
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from typing import Optional

from .models import BalanceRow, PendingOrder, ParsedExport, Trade

TIME_FMT = "%Y.%m.%d %H:%M:%S"
FILLED_TYPES = ("Buy", "Sell")
PENDING_TYPES = ("Buy Stop", "Sell Stop", "Buy Limit", "Sell Limit")


def parse_number(text: str) -> Optional[float]:
    """MQL5-Zahl: Tausenderpunkt-Leerzeichen entfernen, leer -> None."""
    cleaned = text.replace(" ", "").replace("\xa0", "")
    return float(cleaned) if cleaned else None


def parse_time(text: str) -> datetime:
    return datetime.strptime(text.strip(), TIME_FMT)


def _detect_format(header: list[str]) -> str:
    if len(header) >= 13 and any("S/L" in cell for cell in header):
        return "mt4_orderbook"
    return "positions"


def _row_number(row: list[str], idx: int) -> Optional[float]:
    if idx >= len(row):
        return None
    return parse_number(row[idx])


def load_export(path: str) -> ParsedExport:
    """Laedt einen MQL5-Trade-Export (CSV, beide Formate) bzw. ein JSON-Excerpt."""
    if path.lower().endswith(".json"):
        return _load_json_excerpt(path)

    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    if not rows:
        raise ValueError(f"Leere Datei: {path}")
    header = rows[0]
    if not header or header[0].strip() != "Time":
        raise ValueError(
            f"{path}: kein CSV-Export (Header beginnt nicht mit 'Time') — "
            "vermutlich Login-HTML statt Export (Session abgelaufen, siehe doc/02)."
        )
    fmt = _detect_format(header)
    result = ParsedExport(source_path=path, source_format=fmt)

    for row in rows[1:]:
        if len(row) < 11:
            continue
        row_type = row[1].strip()
        if row_type in FILLED_TYPES:
            if fmt == "mt4_orderbook":
                trade = Trade(
                    open_time=parse_time(row[0]), close_time=parse_time(row[7]),
                    direction=row_type, volume=float(row[2]), symbol=row[3],
                    entry_price=_row_number(row, 4), exit_price=_row_number(row, 8),
                    profit=float(_row_number(row, 11) or 0.0),
                    commission=float(_row_number(row, 9) or 0.0),
                    swap=float(_row_number(row, 10) or 0.0),
                    sl=_row_number(row, 5), tp=_row_number(row, 6),
                    comment=(row[12].strip() if len(row) > 12 else ""),
                )
            else:
                trade = Trade(
                    open_time=parse_time(row[0]), close_time=parse_time(row[6]),
                    direction=row_type, volume=float(row[2]), symbol=row[3],
                    entry_price=_row_number(row, 4), exit_price=_row_number(row, 7),
                    profit=float(_row_number(row, 10) or 0.0),
                    commission=float(_row_number(row, 8) or 0.0),
                    swap=float(_row_number(row, 9) or 0.0),
                )
            result.trades.append(trade)
        elif row_type == "Balance":
            amount = _row_number(row, 11 if fmt == "mt4_orderbook" else 10)
            if amount is not None:
                result.balances.append(BalanceRow(time=parse_time(row[0]), amount=amount))
        elif row_type in PENDING_TYPES:
            result.pendings.append(PendingOrder(
                time=parse_time(row[0]), order_type=row_type,
                comment=(row[12].strip() if fmt == "mt4_orderbook" and len(row) > 12 else ""),
            ))
    return result


def _load_json_excerpt(path: str) -> ParsedExport:
    """Trade-Auszug als JSON (z. B. fxtrading_2356441_trades.json).

    Felder: o/c = "YYYY-MM-DD HH:MM", dir = "B"|"S", vol, sym, ep, xp, pnl.
    Keine Kontobewegungen, keine Gebuehren — Ausschnitt, nicht Vollstatistik.
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    result = ParsedExport(source_path=path, source_format="json_excerpt")
    fmt = "%Y-%m-%d %H:%M"
    for item in data:
        direction = "Buy" if item["dir"].upper().startswith("B") else "Sell"
        result.trades.append(Trade(
            open_time=datetime.strptime(item["o"], fmt),
            close_time=datetime.strptime(item["c"], fmt),
            direction=direction, volume=float(item["vol"]), symbol=item["sym"],
            entry_price=item.get("ep"), exit_price=item.get("xp"),
            profit=float(item.get("pnl", 0.0)),
        ))
    return result
