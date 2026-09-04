# -*- coding: utf-8 -*-
"""Kennzahlen von der Signalseite (doc/02 Abschnitt 4).

Werte stehen als Label/Wert-Paare im Seitentext (Label-Zeile gefolgt von
Wert-Zeile(n)). Strategie: HTML -> Textzeilen (bs4 get_text("\\n")), dann
sequentieller Scan ueber bekannte Labels; der Wert ist die Zusammenfassung
der folgenden Zeilen bis zum naechsten Label.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .session import Mql5Session

LABELS = (
    "Growth:", "Profit:", "Equity:", "Balance:", "Initial Deposit:",
    "Withdrawals:", "Deposits:", "Trading Days:", "Latest trade:",
    "Trades per week:", "Avg. holding time:", "Average holding time:",
    "Subscribers:", "Weeks:", "Started:", "Trades:", "Profit Trades:",
    "Loss Trades:", "Best trade:", "Worst trade:", "Gross Profit:",
    "Gross Loss:", "Maximum consecutive wins:", "Maximum consecutive losses:",
    "Maximal consecutive profit:", "Maximal consecutive loss:",
    "Sharpe Ratio:", "Trading activity:", "Max deposit load:",
    "Recovery Factor:", "Long Trades:", "Short Trades:", "Profit Factor:",
    "Expected Payoff:", "Average Profit:", "Average Loss:",
    "Monthly growth:", "Annual Forecast:", "Algo trading:",
    "Absolute:", "Maximal:", "By Balance:", "By Equity:",
)

_LABEL_RE = re.compile(r"^(?:" + "|".join(re.escape(l) for l in LABELS) + r")\s*$")
_BROKER_RE = re.compile(r"\b([A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*)-(Live|Demo|Real)(\d+)\b")
_LEVERAGE_RE = re.compile(r"\b1:(\d{1,5})\b")


def _number(text: str) -> float | None:
    cleaned = text.replace("\xa0", "").replace(" ", "")
    m = re.search(r"-?\d[\d.,]*", cleaned)
    if not m:
        return None
    raw = m.group(0)
    # "1 403.03" -> "1403.03" (Leerzeichen schon weg); Punkte nach der 3. Stelle = Tausender
    if raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        return float(raw.rstrip("."))
    except ValueError:
        return None


def parse_detail_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip()]

    values: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def _flush() -> None:
        # Erstes Vorkommen gewinnt: die Haupt-Statistiksektion hat Vorrang
        # vor der Copy-/Erweitert-Sektion, die dieselben Labels wiederholt.
        if current is not None and current not in values:
            values[current] = " ".join(buffer[:4])

    for line in lines:
        if _LABEL_RE.match(line):
            _flush()
            current = line
            buffer = []
        elif current:
            # Wert endet, wenn eine neue Zeile wie ein Label oder Text beginnt
            if line.endswith(":") or len(buffer) >= 4:
                _flush()
                current = None
                buffer = []
                if line.endswith(":") and _LABEL_RE.match(line):
                    current = line
            else:
                buffer.append(line)
    _flush()

    text_all = "\n".join(lines)
    broker_m = _BROKER_RE.search(text_all)
    leverage_m = _LEVERAGE_RE.search(text_all)

    return {
        "raw": values,
        "growth_pct": _number(values.get("Growth:", "")),
        "profit_abs": values.get("Profit:", ""),
        "equity": values.get("Equity:", ""),
        "balance": values.get("Balance:", ""),
        "initial_deposit": values.get("Initial Deposit:", ""),
        "withdrawals": values.get("Withdrawals:", ""),
        "deposits": values.get("Deposits:", ""),
        "weeks": _number(values.get("Weeks:", "")),
        "trades": _number(values.get("Trades:", "")),
        "profit_trades_pct": _number(values.get("Profit Trades:", "")),
        "loss_trades_pct": _number(values.get("Loss Trades:", "")),
        "worst_trade": _number(values.get("Worst trade:", "")),
        "best_trade": _number(values.get("Best trade:", "")),
        "gross_profit": _number(values.get("Gross Profit:", "")),
        "gross_loss": _number(values.get("Gross Loss:", "")),
        "profit_factor": _number(values.get("Profit Factor:", "")),
        "sharpe": _number(values.get("Sharpe Ratio:", "")),
        "expected_payoff": _number(values.get("Expected Payoff:", "")),
        "max_consecutive_losses": _number(values.get("Maximum consecutive losses:", "")),
        "trading_activity_pct": _number(values.get("Trading activity:", "")),
        "max_deposit_load_pct": _number(values.get("Max deposit load:", "")),
        "recovery_factor": _number(values.get("Recovery Factor:", "")),
        "monthly_growth_pct": _number(values.get("Monthly growth:", "")),
        "algo_trading_pct": _number(values.get("Algo trading:", "")),
        "dd_abs_pct": _number(values.get("Absolute:", "")),
        "dd_max_pct": _number(values.get("Maximal:", "")),
        "dd_balance_pct": _number(values.get("By Balance:", "")),
        "dd_equity_pct": _number(values.get("By Equity:", "")),
        "broker_server": broker_m.group(0) if broker_m else None,
        "leverage": f"1:{leverage_m.group(1)}" if leverage_m else None,
    }


def fetch_signal_stats(session: Mql5Session, signal_id: int) -> dict:
    r = session.get(f"/en/signals/{signal_id}", extra_pause_s=1.0)
    return parse_detail_html(r.text)
