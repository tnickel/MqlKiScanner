"""Strict calculation numbers and persistence-safe result values.

This is deliberately not a source-text parser: locale-specific number strings,
native CSV validation and MQL value extraction retain their own contracts.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
import math


def endliche_zahl(value) -> float | None:
    """Return a finite int/float as float; bool, text and overflow stay unknown."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def ist_endliche_zahl(value) -> bool:
    """Calculation-number predicate with the same contract as endliche_zahl."""
    return endliche_zahl(value) is not None


def json_sicher(value):
    """Normalize calculation results without nonfinite or NumPy values.

    Preserve primitives, render dates as ISO strings, stringify mapping keys,
    and recursively normalize collections and array/scalar protocols. Unknown
    diagnostic objects become text rather than breaking result persistence.
    This matches the existing subscriber-data normalization contract.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_sicher(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_sicher(item) for item in value]
    if hasattr(value, "tolist"):
        return json_sicher(value.tolist())
    if hasattr(value, "item"):
        return json_sicher(value.item())
    return str(value)
