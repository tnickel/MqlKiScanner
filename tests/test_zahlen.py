"""Shared strict helpers must not replace source-specific parsing contracts."""
from collections import UserDict
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import math

import numpy as np
import pytest

from mqlkiscanner.zahlen import endliche_zahl, ist_endliche_zahl, json_sicher


@pytest.mark.parametrize("value", [None, True, False, "1.25", "1,25", [], {},
                                   math.nan, math.inf, -math.inf, 10**1000,
                                   Decimal("1.25"), np.int64(12), np.float32(1.25)])
def test_only_finite_calculation_numbers_are_accepted(value):
    assert endliche_zahl(value) is None
    assert ist_endliche_zahl(value) is False


@pytest.mark.parametrize("value", [0, -1, 2, 0.25, -0.25, np.float64(1.25)])
def test_valid_calculation_numbers_have_one_contract(value):
    assert endliche_zahl(value) == float(value)
    assert isinstance(endliche_zahl(value), float)
    assert ist_endliche_zahl(value) is True


def test_json_normalization_keeps_nested_numpy_dates_and_mappings_serializable():
    class Diagnostic:
        def __str__(self):
            return "unbekannter Diagnosewert"

    value = UserDict({12: (np.array([1.25, np.nan, np.inf]), np.int64(3)),
                      "day": date(2026, 1, 2),
                      "time": datetime(2026, 1, 2, 3, tzinfo=timezone.utc),
                      "flags": [True, None], "diagnostic": Diagnostic(),
                      "set": {4}})
    result = json_sicher(value)
    assert result == {"12": [[1.25, None, None], 3], "day": "2026-01-02",
                      "time": "2026-01-02T03:00:00+00:00", "flags": [True, None],
                      "diagnostic": "unbekannter Diagnosewert", "set": [4]}
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert np.isnan(value[12][0][1])  # The original array is not mutated.


def test_source_text_parsers_keep_their_distinct_locale_contracts():
    from mqlkiscanner import ingest
    from mqlkiscanner.mql5.signal_stats import _number as mql_number

    assert endliche_zahl("9,10") is None
    assert ingest._zahl("9,10") == 9.10
    assert mql_number("9,10") is None
    assert mql_number("1,234.50 USD") == 1234.50
    assert ingest._zahl("1.234,50") == 1234.50


def test_strict_float_acceptance_remains_distinct_from_native_csv_validation():
    from mqlkiscanner.abonnenten_native_cache_import import _number as native_number

    assert endliche_zahl("1.25") is None
    assert native_number("1.25", positive=True) == 1.25
    with pytest.raises(ValueError):
        native_number("nan")
    with pytest.raises(ValueError):
        native_number("0", positive=True)
