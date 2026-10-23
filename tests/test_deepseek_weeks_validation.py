"""Non-finite/invalid source ages must never prove the minimum weeks gate."""
import json

import pytest

from mqlkiscanner import db, ingest, pipeline


INVALID = [None, "", "unknown", "NaN", "Infinity", "-Infinity", float("nan"),
           float("inf"), float("-inf"), -1, "-0.25", True, False, {}, []]


def candidate(raw, route):
    if route == "ingest":
        # Exercise the actual JSON -> source adapter -> pipeline contract.
        item = json.loads(json.dumps({"signalId": "123", "version": "mql5",
                                      "weeks": raw, "subscribers": 10}))
        return ingest.kandidaten({"id": 7, "kuerzel": "mql5"}, [item])[0]
    return {"id": 123, "platform": "MT5", "wochen": raw, "abonnenten": 10}


@pytest.mark.parametrize("route", ["ingest", "direct"])
@pytest.mark.parametrize("raw", INVALID)
@pytest.mark.parametrize("minimum", [0, 26])
def test_invalid_age_is_unproven_and_never_passes_local_weeks_filter(raw, route, minimum):
    entry = candidate(raw, route)
    reasons = []
    selected = pipeline.ScanPipeline({"min_wochen": minimum, "fix_signal_ids": []}).build_candidates(
        [entry], lambda _: None, reasons)
    assert selected == []
    if route == "ingest":
        assert entry["wochen"] is None
    assert "Alter unbekannt" in reasons[0]["grund"]


@pytest.mark.parametrize("route", ["ingest", "direct"])
@pytest.mark.parametrize("raw,allowed", [(0, False), (25.99, False), ("25.99", False),
                                        (26, True), (26.0, True), ("26", True),
                                        (" 26.0 ", True), (52, True), ("52.5", True)])
def test_valid_age_and_numeric_strings_keep_inclusive_26_week_boundary(raw, allowed, route):
    entry = candidate(raw, route)
    selected = pipeline.ScanPipeline({"min_wochen": 26, "fix_signal_ids": []}).build_candidates(
        [entry], lambda _: None)
    assert bool(selected) is allowed
    if allowed:
        assert selected[0]["wochen"] == float(raw)


@pytest.mark.parametrize("route", ["ingest", "direct"])
@pytest.mark.parametrize("raw", INVALID)
def test_fix_id_still_bypasses_age_gate_but_invalid_age_stays_unknown(raw, route):
    entry = candidate(raw, route)
    db.resolve_identity(123, quelle="mql5", create=True)
    reasons = []
    selected = pipeline.ScanPipeline({"min_wochen": 26, "fix_signal_ids": [123]}).build_candidates(
        [entry], lambda _: None, reasons)
    assert len(selected) == 1 and selected[0]["id"] == 123
    assert selected[0]["wochen"] is None
    assert reasons[0]["status"] == "FIX"


@pytest.mark.parametrize("route", ["ingest", "direct"])
def test_zero_is_valid_when_minimum_is_zero(route):
    selected = pipeline.ScanPipeline({"min_wochen": 0, "fix_signal_ids": []}).build_candidates(
        [candidate("0", route)], lambda _: None)
    assert len(selected) == 1 and selected[0]["wochen"] == 0.0
