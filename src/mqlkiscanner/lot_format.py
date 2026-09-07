"""Lot labels preserve source precision and the usual two-decimal display."""
from collections import Counter
from collections.abc import Iterable
from decimal import Decimal


def format_lots(value: float) -> str:
    """Format a finite lot volume without rounding distinct values together."""
    # str(float) retains the shortest representation that round-trips to the
    # original value. Decimal expands scientific notation without rounding.
    text = format(Decimal(str(value)), "f")
    whole, _, fraction = text.partition(".")
    return whole + "." + fraction.rstrip("0").ljust(2, "0")


def lot_histogram(volumes: Iterable[float]) -> dict[str, int]:
    """Distinct volume values remain distinct keys, including sub-cent lots."""
    return {format_lots(value): count for value, count in sorted(Counter(volumes).items())}
