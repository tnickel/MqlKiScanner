# -*- coding: utf-8 -*-
"""Trade-Delta: Was ist seit dem letzten Snapshot hinzugekommen? (Phase B)

Der Vergleich läuft auf zwei Ebenen:
1. Datei-Ebene: SHA-256 des neuen Exports gegen den in trade_files
   gespeicherten Snapshot-Hash — unverändert heißt: keine neuen Trades,
   kein Modellaufruf, keine Kosten.
2. Zeilen-Ebene (nur bei geändertem Hash): Die neuen FILLED-Trades sind
   die Trades des neuen Exports, die im alten nicht vorkommen. Identität
   über die belegten Felder (Zeiten, Richtung, Volumen, Symbol, Preise,
   Profit, Commission, Swap) — nicht über Zeilennummern, denn MQL5 sortiert
   nicht garantiert stabil.

Die Kennzahlen des Deltas berechnet ausschließlich dieser Code (Projekt-
Regel: das LLM zitiert, es rechnet nicht).
"""
from __future__ import annotations

import hashlib
import statistics
from typing import Iterable

from ..models import Trade
from ..parser import load_export


def datei_sha256(pfad: str) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _trade_schluessel(t: Trade) -> tuple:
    return (
        t.open_time, t.close_time, t.direction, round(t.volume, 3),
        t.symbol, t.entry_price, t.exit_price, round(t.profit, 2),
        round(t.commission, 2), round(t.swap, 2),
    )


def neue_trades(alt_pfad: str | None, neu_pfad: str) -> list[Trade]:
    """Gefüllte Trades, die im neuen Export, aber nicht im alten sind.

    Ohne alt_pfad (erstes Delta eines Signals) zählt der komplette Export
    als neu — das Dossier beginnt dann mit der Gesamtzahl.
    """
    alt: list[Trade] = load_export(alt_pfad).trades if alt_pfad else []
    neu = load_export(neu_pfad).trades
    alt_schluessel = {_trade_schluessel(t) for t in alt}
    return [t for t in neu if _trade_schluessel(t) not in alt_schluessel]


def kennzahlen(trades: list[Trade]) -> dict:
    """Maschinelle Delta-Kennzahlen für den Betreuer-Prompt."""
    if not trades:
        return {"anzahl": 0}
    profits = [t.profit for t in trades]
    volumen = [t.volume for t in trades]
    gewinne = [p for p in profits if p > 0]
    verluste = [p for p in profits if p < 0]
    # Uhrzeiten (lokale Exportzeit) und Tage — Sessions erkennbar?
    stunden = sorted({t.open_time.hour for t in trades})
    tage = sorted({t.open_time.strftime("%Y-%m-%d") for t in trades})
    # Verlustserien im Delta (max. Länge in Folge, chronologisch)
    max_serie = 0
    serie = 0
    for t in sorted(trades, key=lambda x: x.close_time):
        serie = serie + 1 if t.profit < 0 else 0
        max_serie = max(max_serie, serie)
    return {
        "anzahl": len(trades),
        "zeitraum": [tage[0], tage[-1]],
        "symbole": sorted({t.symbol for t in trades}),
        "richtung": {"Buy": sum(1 for t in trades if t.direction == "Buy"),
                     "Sell": sum(1 for t in trades if t.direction == "Sell")},
        "stunden_offen": stunden,
        "volumen": {"min": min(volumen), "median": statistics.median(volumen),
                    "max": max(volumen), "netto": round(sum(
                        t.volume if t.direction == "Buy" else -t.volume
                        for t in trades), 3)},
        "gewinne": len(gewinne),
        "verluste": len(verluste),
        "gewinnsumme": round(sum(gewinne), 2),
        "verlustsumme": round(sum(verluste), 2),
        "netto": round(sum(profits), 2),
        "max_verlustserie": max_serie,
    }
