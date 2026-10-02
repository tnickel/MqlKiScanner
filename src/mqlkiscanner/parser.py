# -*- coding: utf-8 -*-
"""Parser fuer MQL5-Trade-Exporte.

Zwei CSV-Varianten (doc/02_technik-mql5.md Abschnitt 3):
- Positions-Export (11 Spalten, Profit = Idx 10, Close = Idx 6/7)
- MT4-Orderbuch (13 Spalten, S/L = Idx 5, T/P = Idx 6, Profit = Idx 11,
  Kommentar = Idx 12)

Fallstricke, die hier behandelt werden:
- Tausendertrennzeichen als Leerzeichen bzw. NBSP ("1 403.03")
- Beschaedigte Datensaetze werden mit Zeilennummer abgelehnt
- Balance-Zeilen: Betrag steht in der Profit-Spalte des jeweiligen Formats
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from typing import Optional

from .models import BalanceRow, PendingOrder, ParsedExport, Trade

TIME_FMT = "%Y.%m.%d %H:%M:%S"
FILLED_TYPES = ("Buy", "Sell")
PENDING_TYPES = ("Buy Stop", "Sell Stop", "Buy Limit", "Sell Limit")
POSITION_HEADER = ("Time", "Type", "Volume", "Symbol", "Price", "Volume",
                   "Time", "Price", "Commission", "Swap", "Profit")
ORDERBOOK_HEADER = ("Time", "Type", "Volume", "Symbol", "Price", "S/L", "T/P",
                   "Time", "Price", "Commission", "Swap", "Profit", "Comment")


def parse_number(text: str) -> Optional[float]:
    """MQL5-Zahl: Tausenderpunkt-Leerzeichen entfernen, leer -> None."""
    cleaned = text.replace(" ", "").replace("\xa0", "")
    value = float(cleaned) if cleaned else None
    if value is not None and not math.isfinite(value):
        raise ValueError("Zahl ist nicht endlich")
    return value


def parse_time(text: str) -> datetime:
    return datetime.strptime(text.strip(), TIME_FMT)


def _detect_format(header: list[str]) -> str:
    # Field positions below are fixed. Width alone cannot prove their meaning
    # (e.g. swapped S/L and T/P must never turn take profits into stop proof).
    columns = tuple(cell.strip() for cell in header)
    if columns == ORDERBOOK_HEADER:
        return "mt4_orderbook"
    if columns == POSITION_HEADER:
        return "positions"
    raise ValueError("unvollstaendiger oder unbekannter CSV-Header")


def _row_number(row: list[str], idx: int) -> Optional[float]:
    if idx >= len(row):
        return None
    return parse_number(row[idx])


def profit_idx_for(fmt: str) -> int:
    return 11 if fmt == "mt4_orderbook" else 10


def _is_mt4_summary_row(row: list[str], fmt: str) -> bool:
    """MT4-Orderbuch-Footer: 'Buy;0.10;profit;;;;<close>;;;<comm>;<gesamtsumme>'.

    Erkannt an Typ Buy/Sell MIT Symbol 'profit' (case-insensitiv) und leeren
    Preisfeldern. Ein echter Trade ohne Preise bleibt ein Fehler; ein echtes
    Instrument mit Namen 'profit' gibt es nicht — die leeren Preise sichern
    die Erkennung gegen False Positives ab.
    """
    row_type = row[1].strip()
    if row_type not in FILLED_TYPES or row[3].strip().casefold() != "profit":
        return False
    if fmt == "mt4_orderbook":
        return not (row[4].strip() or row[8].strip())
    return not (row[4].strip() or row[7].strip())


def load_export(path: str) -> ParsedExport:
    """Laedt einen MQL5-Trade-Export (CSV, beide Formate) bzw. ein JSON-Excerpt."""
    if path.lower().endswith(".json"):
        return _load_json_excerpt(path)

    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    if not rows:
        raise ValueError(f"Leere Datei: {path}")
    # B25 (Lauf-Review 02.10.): Exakte Zeilen-Duplikate bei MASSIERTem
    # Auftreten entfernen, BEVOR geparst wird. Zwei belegte reale Phänomene:
    # (a) Liefer-Duplikate ganzer Historienteile aus Datenquellen-Monitoren
    # (The Holy Grail: 4.197/15.340 = 27,4 % — Drawdown systematisch nach
    # unten verfälscht); (b) ECHTE Zwillings-Grid-Legs (F-16, Multiset:
    # Gold-Spike-MT5-Referenz matched 98 NUR mit Zwillingen — dort 2 exakte
    # Duplikate, echt). Unterscheidbar sind beide nur über die MASSE:
    # bereinigt wird erst ab MIN_DEDUPLICATE (10+) Zeilen UND >= 1 % Anteil
    # — echte Einzelfall-Zwillinge bleiben zählen, Massen-Doppellieferungen
    # werden entfernt. Der Zähler geht in den Forensik-Befund.
    gesehen: set[tuple[str, ...]] = set()
    mit_duplikaten: list[list[str]] = [rows[0]]
    ohne_duplikate: list[list[str]] = [rows[0]]
    roh_doppelte = 0
    for zeile in rows[1:]:
        mit_duplikaten.append(zeile)
        schluessel = tuple(zelle.strip() for zelle in zeile)
        if schluessel in gesehen and any(schluessel):
            roh_doppelte += 1
            continue
        gesehen.add(schluessel)
        ohne_duplikate.append(zeile)
    datenzeilen = max(len(rows) - 1, 1)
    if roh_doppelte >= 10 and roh_doppelte / datenzeilen >= 0.01:
        rows = ohne_duplikate
        doppelte = roh_doppelte
    else:
        rows = mit_duplikaten
        doppelte = 0
    header = rows[0]
    if not header or header[0].strip() != "Time":
        raise ValueError(
            f"{path}: kein CSV-Export (Header beginnt nicht mit 'Time') — "
            "vermutlich Login-HTML statt Export (Session abgelaufen, siehe doc/02)."
        )
    try:
        fmt = _detect_format(header)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    expected_columns = 13 if fmt == "mt4_orderbook" else 11
    profit_idx = profit_idx_for(fmt)
    result = ParsedExport(source_path=path, source_format=fmt,
                          duplikate_entfernt=doppelte)

    for line, row in enumerate(rows[1:], start=2):
        if not row or not any(cell.strip() for cell in row):
            continue
        # B6 (Intensiv-Review 29./30.09.2026): Eine unvollstaendige LETZTE
        # Datenzeile ist meist ein ABGEBROCHENER Download (Beleg: Signal
        # 840474, "Zeile 9220: Pflichtfeld fehlt (Buy)") — bewusst KEIN
        # Skip-Tolerieren: Ein teilweise geladener Export muss ungültig
        # bleiben (Cache-Poisoning-Abwehr, tests/test_second_review_
        # ingestion), sonst sieht ein halber Download wie eine voll-
        # staendige, einfach ruhigere Historie aus. Der Fehlertext nennt
        # stattdessen die wahrscheinliche Ursache.
        tail_hint = (" — letzte Datenzeile: Download vermutlich unvollständig, "
                     "erneut laden" if line == len(rows) else "")
        if len(row) != expected_columns:
            raise ValueError(f"{path}: Zeile {line}: {len(row)} statt "
                             f"{expected_columns} Felder (unvollstaendiger "
                             f"Export){tail_hint}")
        row_type = row[1].strip()
        if not row_type:
            # MT5-Exporte enthalten vereinzelt Zeilen mit NUR einem Zeitstempel
            # (Beleg: Signal 2271995, Zeilen 222/391 — kein Typ, Volumen, Symbol
            # oder Geldwert). Solche Zeilen tragen keine analytische Information
            # und werden uebersprungen; Inhalt ohne Typ bleibt ein lauter Fehler.
            trade_fields = ([2, 3, 4, 7, 8, profit_idx] if fmt == "mt4_orderbook"
                            else [2, 3, 4, 6, 7, profit_idx])
            if any(row[idx].strip() for idx in trade_fields):
                raise ValueError(f"{path}: Zeile {line}: Datensatz ohne Typ "
                                 f"mit Inhalt (defekte Zeile)")
            continue
        # B6-Nachtrag: abgebrochene LETZTE Zeile in voller Breite (Pflichtfeld
        # leer) — derselbe Truncation-Fall, ebenfalls bewusst lauter Fehler.
        if _is_mt4_summary_row(row, fmt):
            # MT4-Orderbuch-Footer: Typ Buy/Sell, Symbol 'profit', keine Preise,
            # Profit-Spalte = Gesamtsumme. Kein Trade — sonst verfaelscht die
            # Summe als Riesen-Trade jede Statistik.
            continue
        # B6 (Intensiv-Review): MT4-History kennt neben Balance/Credit den
        # Datensatztyp 'Correction' (Broker-Korrektur, Betrag in der Profit-
        # Spalte; Beleg: Signal 2268766, "unbekannter Datensatztyp 'Correction'").
        # Semantik wie eine Kontobewegung, kein Trade.
        if row_type not in (*FILLED_TYPES, *PENDING_TYPES,
                            "Balance", "Credit", "Correction"):
            raise ValueError(f"{path}: Zeile {line}: unbekannter Datensatztyp {row_type!r}")
        required = [0, 1]
        if row_type in FILLED_TYPES:
            required += [2, 3, 4, 7, 8, profit_idx] if fmt == "mt4_orderbook" else [2, 3, 4, 6, 7, profit_idx]
        elif row_type in ("Balance", "Credit", "Correction"):
            required.append(profit_idx)
        if any(not row[idx].strip() for idx in required):
            raise ValueError(f"{path}: Zeile {line}: Pflichtfeld fehlt "
                             f"({row_type}){tail_hint}")
        if row_type in FILLED_TYPES:
            if fmt == "mt4_orderbook":
                trade = Trade(
                    open_time=parse_time(row[0]), close_time=parse_time(row[7]),
                    direction=row_type, volume=parse_number(row[2]), symbol=row[3].strip(),
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
                    direction=row_type, volume=parse_number(row[2]), symbol=row[3].strip(),
                    entry_price=_row_number(row, 4), exit_price=_row_number(row, 7),
                    profit=float(_row_number(row, 10) or 0.0),
                    commission=float(_row_number(row, 8) or 0.0),
                    swap=float(_row_number(row, 9) or 0.0),
                )
            if trade.volume <= 0 or trade.close_time < trade.open_time:
                raise ValueError(f"{path}: Zeile {line}: ungueltiges Volumen oder Handelszeitraum")
            result.trades.append(trade)
        elif row_type in ("Balance", "Correction"):
            amount = _row_number(row, profit_idx)
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
    if not isinstance(data, list):
        raise ValueError(f"{path}: JSON-Auszug muss eine Liste von Trades enthalten")
    result = ParsedExport(source_path=path, source_format="json_excerpt")
    fmt = "%Y-%m-%d %H:%M"
    directions = {"B": "Buy", "BUY": "Buy", "S": "Sell", "SELL": "Sell"}
    for index, item in enumerate(data, start=1):
        try:
            if not isinstance(item, dict):
                raise ValueError("Trade muss ein JSON-Objekt sein")
            for key in ("o", "c", "dir", "vol", "sym", "pnl"):
                if key not in item or item[key] is None:
                    raise ValueError(f"Pflichtfeld fehlt: {key}")
            if not isinstance(item["dir"], str) or item["dir"].strip().upper() not in directions:
                raise ValueError("ungueltige Richtung (erwartet B/S oder Buy/Sell)")
            if not isinstance(item["sym"], str) or not item["sym"].strip():
                raise ValueError("Instrument fehlt oder ist kein Text")
            trade = Trade(
                open_time=datetime.strptime(item["o"], fmt),
                close_time=datetime.strptime(item["c"], fmt),
                direction=directions[item["dir"].strip().upper()],
                volume=_json_number(item["vol"], required=True), symbol=item["sym"].strip(),
                entry_price=_json_number(item.get("ep")), exit_price=_json_number(item.get("xp")),
                profit=_json_number(item["pnl"], required=True),
            )
            if trade.volume <= 0 or trade.close_time < trade.open_time:
                raise ValueError("ungueltiges Volumen oder Handelszeitraum")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path}: Trade {index}: {exc}") from exc
        result.trades.append(trade)
    return result


def _json_number(value, *, required: bool = False) -> Optional[float]:
    """Apply the CSV finite-number contract to excerpt numbers as well."""
    if value is None:
        number = None
    elif isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("ungueltige Zahl")
    else:
        number = parse_number(str(value).strip())
    if required and number is None:
        raise ValueError("numerisches Pflichtfeld ist leer")
    return number
