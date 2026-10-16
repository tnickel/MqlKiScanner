# -*- coding: utf-8 -*-
"""Datenmodelle fuer MQL5-Trade-Exporte (Spec: doc/02_technik-mql5.md Abschnitt 3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import math


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
class AccountCostRow:
    """Separate Kontokosten/-erstattungen, KEIN externer Kapitalfluss."""
    time: datetime
    amount: float
    kind: str


@dataclass
class PendingOrder:
    """Pending-Order (Buy/Sell Stop/Limit) — nur Orderbuch-Format."""
    time: datetime
    order_type: str
    comment: str = ""


@dataclass
class ArchivedPnlAggregate:
    """Original-Monatsaggregat: Finanzbetrag, keine einzelne Position."""
    period_start: datetime
    period_end: datetime
    volume: float
    profit: float
    commission: float
    swap: float
    source_line: int

    @property
    def net(self) -> float:
        return math.fsum((self.profit, self.commission, self.swap))


@dataclass
class ParsedExport:
    """Ergebnis des Parsers: Trades, Kontobewegungen, Pendings + Format."""
    source_path: str
    source_format: str            # "mt4_orderbook" | "positions" | "json_excerpt"
    trades: list[Trade] = field(default_factory=list)
    balances: list[BalanceRow] = field(default_factory=list)
    pendings: list[PendingOrder] = field(default_factory=list)
    # Legacy-Auditfeld; ticketlose CSV-Zeilen werden seit 03.10. erhalten.
    duplikate_entfernt: int = 0
    identische_tradezeilen: int = 0  # Hinweis, kein Identitaets-/Duplikatbeweis
    neutrale_hedge_metazeilen: int = 0  # belegte MT4-Close-by-Verwaltungsereignisse
    costs: list[AccountCostRow] = field(default_factory=list)
    # Nur Finanzlesemodus: kein belegter individueller Realisierungszeitpunkt.
    archived_pnl_aggregates: list[ArchivedPnlAggregate] = field(default_factory=list)

    def realized_events(self) -> list[tuple[datetime, float]]:
        """Alle realisierten Ergebnisse; separate Buchungen nie deduplizieren."""
        return sorted([(t.close_time, t.net) for t in self.trades]
                      + [(c.time, c.amount) for c in self.costs], key=lambda e: e[0])

    @property
    def net_total(self) -> float:
        return math.fsum(amount for _, amount in self.realized_events())

    @property
    def has_orderbook(self) -> bool:
        return self.source_format == "mt4_orderbook"
