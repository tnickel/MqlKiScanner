"""Conservative instrument names and quote units; unknown contracts stay unknown."""
from __future__ import annotations

import re


_CURRENCIES = frozenset((
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SGD", "HKD",
    "CNH", "CNY", "NOK", "SEK", "DKK", "ZAR", "MXN", "TRY", "PLN", "HUF",
    "CZK", "RUB",
))
_INDEX_ALIASES = {
    "US30": "US30", "US500": "US500", "SPX500": "US500", "SPX": "US500",
    "US100": "US100", "NAS100": "US100", "NDX": "US100",
    "GER40": "GER40", "UK100": "UK100", "JP225": "JP225", "CHINA50": "CHINA50",
}
_KNOWN = tuple(sorted({"XAUUSD", *_INDEX_ALIASES}, key=len, reverse=True))
_BROKER_SUFFIX = re.compile(r"(?:[._+\-][A-Z0-9._+\-]*|M|R|C|PRO|RAW|ECN|MICRO|CENT)?$")


def normalize_symbol(symbol: str) -> str:
    """Remove explicit broker suffixes only from recognized instruments.

    Arbitrary prefixes/substrings are deliberately not treated as instruments:
    e.g. EURUSDT must not silently become EURUSD.
    """
    value = (symbol or "").strip().upper()
    if (len(value) >= 6 and value[:3] in _CURRENCIES
            and value[3:6] in _CURRENCIES and value[:3] != value[3:6]
            and _BROKER_SUFFIX.fullmatch(value[6:])):
        return value[:6]
    for core in _KNOWN:
        if value.startswith(core) and _BROKER_SUFFIX.fullmatch(value[len(core):]):
            return _INDEX_ALIASES.get(core, core)
    return value


def fx_pip_size(symbol: str) -> float | None:
    value = normalize_symbol(symbol)
    if (len(value) == 6 and value[:3] in _CURRENCIES and value[3:] in _CURRENCIES
            and value[:3] != value[3:]):
        return 0.01 if value[3:] == "JPY" else 0.0001
    return None


def symbol_class(symbol: str) -> str:
    value = normalize_symbol(symbol)
    if value == "XAUUSD":
        return "METAL"
    if value in _INDEX_ALIASES.values():
        return "INDEX"
    if fx_pip_size(value) is not None:
        return "FX"
    return "UNKNOWN"
