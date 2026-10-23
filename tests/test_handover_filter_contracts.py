"""Independent selection oracles for the supplemental review catalogue."""
import itertools
from pathlib import Path

import pytest

from mqlkiscanner import config, db, fix_signale, ingest, pipeline


def test_equal_subscriber_counts_select_same_ids_for_every_catalogue_order():
    candidates = [{"id": sid, "abonnenten": 7, "quelle_kuerzel": "pelican"}
                  for sid in (30, 10, 20)]
    for order in itertools.permutations(candidates):
        selected, _ = fix_signale.waehle_fuer_export(list(order), 2, {"fix_signal_ids": []})
        assert [item["id"] for item in selected] == [10, 20]


@pytest.mark.parametrize("route", ["direct", "ingest"])
@pytest.mark.parametrize("raw", [None, "", "unknown", float("nan"), float("inf"),
                                 -1, True, False, 1.5, {}, []])
def test_invalid_subscriber_count_cannot_prove_one_subscriber(route, raw):
    candidate = {"id": 123, "wochen": 52, "abonnenten": raw}
    if route == "ingest":
        candidate = ingest.kandidaten({"id": 2, "kuerzel": "pelican"},
            [{"signalId": 123, "version": "pelican", "weeks": 52, "subscribers": raw}])[0]
    reasons = []
    selected = pipeline.ScanPipeline({"min_abonnenten": 1, "fix_signal_ids": []}).build_candidates(
        [candidate], lambda _: None, reasons)
    assert selected == []
    assert reasons[0]["abonnenten"] is None
    assert "unbekannt" in reasons[0]["grund"]


@pytest.mark.parametrize("raw", [0, 1, 1.0, "1", " 7 "])
def test_known_subscriber_counts_keep_inclusive_boundary(raw):
    selected = pipeline.ScanPipeline({"min_abonnenten": 1, "fix_signal_ids": []}).build_candidates(
        [{"id": 123, "wochen": 52, "abonnenten": raw}], lambda _: None)
    assert bool(selected) is (float(raw) >= 1)


def test_unknown_subscribers_remain_allowed_when_subscriber_filter_disabled():
    reasons = []
    selected = pipeline.ScanPipeline({"min_abonnenten": 0, "fix_signal_ids": []}).build_candidates(
        [{"id": 123, "wochen": 52, "abonnenten": None}], lambda _: None, reasons)
    assert len(selected) == 1
    assert selected[0]["abonnenten"] is None
    assert "unbekannt" in reasons[0]["grund"]
    assert "0 Abonnenten" not in reasons[0]["grund"]


def test_fix_id_bypasses_subscriber_filter_without_inventing_count():
    db.resolve_identity(123, quelle="mql5", create=True)
    selected = pipeline.ScanPipeline({"min_abonnenten": 1, "fix_signal_ids": [123]}).build_candidates(
        [{"id": 123, "wochen": 52, "abonnenten": float("nan")}], lambda _: None)
    assert selected[0]["abonnenten"] is None


def test_scan_settings_preserve_fractional_minimum_weeks():
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parents[1]
    config.save_settings({**config.load_settings(), "min_wochen": 26.5})
    app = AppTest.from_file(str(root / "streamlit_app.py"), default_timeout=60).run()
    assert not app.exception
    app.switch_page("app_pages/scan.py").run()
    assert not app.exception
    assert app.number_input(key="set_wochen").value == 26.5
    app.button(key="scan_save").click().run()
    assert not app.exception
    assert config.load_settings()["min_wochen"] == 26.5
