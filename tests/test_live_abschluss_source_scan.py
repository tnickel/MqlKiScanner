"""Exercise real maintenance selection with isolated storage and no source access."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from mqlkiscanner import analysis_version, config, db, fix_signale, ingest, pipeline
from mqlkiscanner.agenten import scan_launcher
from mqlkiscanner import client_updates


def _head(sid, source="alpha", platform="MT5", **kwargs):
    return {"signal_id": sid, "signal_ref": 100 + sid, "quelle": source,
            "quellen_uid": "uid-" + source, "platform": platform, "name": f"head-{sid}",
            "abonnenten": 0, "wochen": 0, **kwargs}


def _item(sid, version="mql5", subscribers=100, weeks=30):
    return {"signalId": sid, "signalName": f"item-{sid}", "version": version,
            "subscribers": subscribers, "weeks": weeks}


@pytest.fixture
def source_scan(monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/reference/live_abschluss.py"
    spec = importlib.util.spec_from_file_location("live_abschluss_source_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = config.DATA_DIR / "runs" / "source-scan-test"
    source = {"id": 11, "kuerzel": "alpha", "quellen_uid": "uid-alpha", "aktiv": True}
    state = {"items": [], "heads": [], "analyzed": [], "cleanup": 0, "sources": [source]}
    settings = {"top_n_export": 1, "min_wochen": 26, "min_abonnenten": 1, "fix_signal_ids": []}
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    monkeypatch.setattr(config, "load_known_signals", lambda: {})
    monkeypatch.setattr(fix_signale, "fix_keys", lambda settings=None: set())
    monkeypatch.setattr(db, "list_quellen", lambda **kwargs: state["sources"])
    monkeypatch.setattr(db, "list_catalog", lambda: state["heads"])
    monkeypatch.setattr(ingest, "hole_katalog", lambda source: state["items"])
    original_pipeline = pipeline.ScanPipeline

    class TestPipeline:
        def __init__(self, settings, quelle, *, allow_offline_source_cache):
            assert allow_offline_source_cache is False
            self.settings = settings

        # Use production filters; only forensics/terminal operations are mocked.
        build_candidates = original_pipeline.build_candidates

        def analyze_candidate(self, session, candidate, log):
            assert session is None
            state["analyzed"].append(candidate)
            if state.get("analysis_error"):
                raise RuntimeError("simulated forensics failure")
            return SimpleNamespace(quelle=candidate["quelle_kuerzel"], id=candidate["id"],
                                   forensik_vorhanden=True, persisted_this_run=True,
                                   fehler="", ampel="🟡", equity_rekon_status="ok")

        def kursdaten_beenden(self):
            state["cleanup"] += 1

    monkeypatch.setattr(pipeline, "ScanPipeline", TestPipeline)

    def no_second_update(*args, **kwargs):
        raise AssertionError("source-scan must never start another Stufe-0/full scan")

    monkeypatch.setattr(client_updates, "starte_alle_updates", no_second_update)
    monkeypatch.setattr(scan_launcher, "starte_scan", no_second_update)

    def run(source="alpha", version=None, ids=None):
        argv = [str(script), "source-scan", "--live", "--expected-version",
                str(analysis_version.FORENSICS_VERSION if version is None else version),
                "--output", str(output)]
        if source is not None:
            argv += ["--source", source]
        if ids is not None:
            argv += ["--ids", ids]
        monkeypatch.setattr(sys, "argv", argv)
        module.main()
        return json.loads((output / f"source-scan_{source}.json").read_text(encoding="utf-8"))

    return state, run


def test_explicit_known_maintenance_id_bypasses_only_export_prefilters(source_scan):
    state, run = source_scan
    state["items"] = [_item(1, subscribers=100), _item(2, subscribers=0, weeks=0)]
    receipt = run(ids="2")
    assert [row["id"] for row in state["analyzed"]] == [2]
    assert receipt["requested_ids"] == [2]


def test_explicit_unknown_maintenance_id_is_not_invented(source_scan):
    state, run = source_scan
    state["items"] = [_item(1)]
    receipt = run(ids="999")
    assert not state["analyzed"]
    assert receipt["result"]["blocked"][0]["id"] == 999


def test_normal_filters_and_top_n_then_all_old_workflow_heads_of_only_this_source(source_scan):
    state, run = source_scan
    state["items"] = [_item(1), _item(2, subscribers=50), _item(3, subscribers=1000, weeks=1)]
    state["heads"] = [_head(1), _head(2), _head(4), _head(1, "other"), _head(4)]
    receipt = run()
    assert [c["id"] for c in state["analyzed"]] == [1, 2, 4]
    assert {c["quelle_kuerzel"] for c in state["analyzed"]} == {"alpha"}
    assert {c["quellen_uid"] for c in state["analyzed"]} == {"uid-alpha"}
    assert state["analyzed"][1]["signal_ref"] == 102
    assert receipt["result"]["attempted"] == 3
    assert receipt["result"]["selection"] == [{"quelle": "alpha", "angeboten": 2, "genommen": 1}]
    assert state["cleanup"] == 1


@pytest.mark.parametrize("platform,expected", [("MT4", "mql4"), ("MT5", "mql5"),
    ("mql4", "mql4"), ("MQL5", "mql5"), ("Vantage", "vantage"),
    ("pelican", "pelican"), ("Zulu", "zulu")])
def test_old_heads_keep_their_explicit_supported_platform_version(source_scan, platform, expected):
    state, run = source_scan
    state["heads"] = [_head(7, platform=platform)]
    run()
    assert state["analyzed"][0]["quelle_version"] == expected


@pytest.mark.parametrize("platform", [None, "", "UNKNOWN", "CSV"])
def test_unknown_old_platform_must_not_reach_mql5_fallback(source_scan, platform):
    state, run = source_scan
    state["heads"] = [_head(7, platform=platform)]
    try:
        run()
    except RuntimeError as exc:
        assert "platform" in str(exc).lower() or "plattform" in str(exc).lower() or "version" in str(exc).lower()
    assert state["analyzed"] == [], "unproven platform must never become a native mql5 request"


def test_conflicting_live_catalog_platforms_cannot_be_reintroduced_from_old_head(source_scan):
    state, run = source_scan
    state["items"] = [_item(7, "mql4"), _item(7, "mql5")]
    state["heads"] = [_head(7, platform="MT4")]
    receipt = run()
    assert state["analyzed"] == [], "old head must not bypass source-scoped live identity conflict"
    assert receipt["result"]["blocked"][0]["id"] == 7


@pytest.mark.parametrize("version", ["UNKNOWN", "", "MQL5", "mql6"])
def test_invalid_catalog_version_never_reaches_forensic_source_endpoint(source_scan, version):
    state, run = source_scan
    state["items"] = [_item(7, version=version)]
    receipt = run()
    assert state["analyzed"] == []
    assert receipt["result"]["blocked"][0]["id"] == 7


def test_selected_candidate_with_mismatching_version_and_platform_is_explicitly_blocked(source_scan, monkeypatch):
    state, run = source_scan
    state["items"] = [_item(7)]
    original_select = fix_signale.waehle_fuer_export

    def contradict(*args, **kwargs):
        selected, info = original_select(*args, **kwargs)
        assert selected[0]["platform"].upper() == "MT5"
        selected[0]["quelle_version"] = "mql4"
        return selected, info

    monkeypatch.setattr(fix_signale, "waehle_fuer_export", contradict)
    receipt = run()
    assert state["analyzed"] == []
    assert receipt["result"]["blocked"][0]["id"] == 7


def test_analysis_failure_still_cleans_up_terminal_and_does_not_claim_success(source_scan):
    state, run = source_scan
    state["heads"] = [_head(7)]
    state["analysis_error"] = True
    with pytest.raises(RuntimeError, match="simulated"):
        run()
    assert state["cleanup"] == 1


@pytest.mark.parametrize("source,duplicate,version_mismatch", [(None, False, False),
    ("missing", False, False), ("alpha", True, False), ("alpha", False, True)])
def test_invalid_source_or_code_version_stops_before_any_forensic_request(source_scan, source, duplicate, version_mismatch):
    state, run = source_scan
    if duplicate:
        state["sources"] *= 2
    with pytest.raises(RuntimeError):
        run(source=source, version=-1 if version_mismatch else None)
    assert state["analyzed"] == []
