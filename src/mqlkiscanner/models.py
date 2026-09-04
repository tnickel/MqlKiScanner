# -*- coding: utf-8 -*-
"""Datenmodelle fuer MQL5-Trade-Exporte (Spec: doc/02_technik-mql5.md Abschnitt 3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Trade:
    """Abgeschlossene Position (gefuellt) aus einem Trade-Export."""
    open_time: datetime
    close_time: datetime
    direction: str            # "Buy" | "Sell"
    volume: float             # Lots
    symbol: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    profit: float             # Spalte "Profit" (ohne Komm/Swap)
    commission: float = 0.0
    swap: float = 0.0
    sl: Optional[float] = None   # nur Orderbuch-Format
    tp: Optional[float] = None   # nur Orderbuch-Format
    comment: str = ""            # nur Orderbuch-Format: "[sl]", "[tp]", "cancelled", ...

    @property
    def net(self) -> float:
        """Netto-Ergebnis der Position inkl. Kommission und Swap."""
        return self.profit + self.commission + self.swap

    @property
    def is_win(self) -> bool:
        return self.profit > 0

    @property
    def holding_hours(self) -> float:
        return (self.close_time - self.open_time).total_seconds() / 3600.0

    @property
    def sign(self) -> int:
        return 1 if self.direction == "Buy" else -1

    def loss_distance(self) -> Optional[float]:
        """Preis-Distanz eines Verlustes in Kurspunkten (positiv), sonst None."""
        if self.profit >= 0 or self.entry_price is None or self.exit_price is None:
            return None
        d = (self.entry_price - self.exit_price) * self.sign
        return d if d > 0 else None


@dataclass
class BalanceRow:
    """Kontobewegung (Einzahlung/Auszahlung/Gutschrift), Typ=Balance."""
    time: datetime
    amount: float


@dataclass
class PendingOrder:
    """Pending-Order (Buy/Sell Stop/Limit) — nur Orderbuch-Format."""
    time: datetime
    order_type: str
    comment: str = ""


@dataclass
class ParsedExport:
    """Ergebnis des Parsers: Trades, Kontobewegungen, Pendings + Format."""
    source_path: str
    source_format: str            # "mt4_orderbook" | "positions" | "json_excerpt"
    trades: list[Trade] = field(default_factory=list)
    balances: list[BalanceRow] = field(default_factory=list)
    pendings: list[PendingOrder] = field(default_factory=list)

    @property
    def has_orderbook(self) -> bool:
        return self.source_format == "mt4_orderbook"
