"""A concurrent cache refresh must never rebind old findings to new bytes."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from mqlkiscanner import config, db, engine, katalog, pipeline, quellen
from mqlkiscanner.agenten import lock


CSV_A = (
    "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
    "2023.12.31 10:00:00;Balance;;;;;;;;;;1000;\n"
    "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.01 11:00:00;2001;0;0;1;\n"
    "2024.01.02 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.02 11:00:00;1999;0;0;-1;\n"
)
CSV_B = CSV_A + "2024.05.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.05.01 11:00:00;2010;0;0;10;\n"


@pytest.fixture
def safe_scan(monkeypatch):
    db.init_db()
    monkeypatch.setattr(pipeline.fx_rates, "status", lambda: {"geladen": False})
    monkeypatch.setattr(pipeline.ScanPipeline, "_kursanbieter_fuer", lambda *a: None)
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", lambda *a: {
        "account_currency": "USD", "initial_deposit_usd": 1000,
        "dd_equity_pct": 5, "monthly_growth_pct": 10})
    return pipeline.ScanPipeline({"equity_rekonstruktion": False})


def test_manual_source_refresh_during_analysis_keeps_one_snapshot(safe_scan, monkeypatch):
    """Actual ingest + manual load interleave deterministically across threads."""
    source_id = db.add_quelle("synthetic", "Synthetic source", "http://127.0.0.1:1")
    signal_id = 910018
    manual = pipeline.ScanResult(id=signal_id, quelle="synthetic", quelle_id=source_id,
                                  quelle_version="mql5", platform="MT5")
    payloads = iter((CSV_A.encode(), CSV_B.encode()))

    class FakeSource:
        def metrics(self, *args):
            return {"signalId": signal_id, "version": "mql5", "metrics": {
                "Currency": "USD", "InitialDeposit": 1000, "EquityDrawdown": 5}}

        def trades_csv(self, *args):
            return next(payloads)

    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda *_: FakeSource())
    analyzed, refreshed = Event(), Event()
    original = pipeline.analyze_export
    analyzed_paths, return_paths = [], []

    def analyze_then_wait(path, *args, **kwargs):
        analyzed_paths.append(path)
        report = original(path, *args, **kwargs)
        analyzed.set()
        assert refreshed.wait(10), "Manual refresh did not finish"
        return report

    original_efficiency = pipeline.portfolio_statistik.effizienz_kennzahlen

    def record_efficiency(path, *args, **kwargs):
        return_paths.append(path)
        return original_efficiency(path, *args, **kwargs)

    monkeypatch.setattr(pipeline, "analyze_export", analyze_then_wait)
    monkeypatch.setattr(pipeline.portfolio_statistik, "effizienz_kennzahlen", record_efficiency)

    def scan():
        with lock.lauf_lock(config.DATA_DIR):
            return safe_scan._analyze_candidate_once(None, {
                "id": signal_id, "platform": "MT5", "quelle_id": source_id,
                "quelle_kuerzel": "synthetic", "quelle_version": "mql5"}, lambda _: None)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(scan)
        try:
            assert analyzed.wait(10), "Scanner did not reach analysis"
            cache_path, changed = katalog.lade_signal_daten(manual)
            assert changed and Path(cache_path).read_text(encoding="utf8") == CSV_B
        finally:
            refreshed.set()
        result = pending.result(timeout=10)

    assert not result.fehler and result.forensik_vorhanden and result.persisted_this_run
    row = db.list_catalog()[0]
    saved = engine.analyze(row["trades_path"])
    assert Path(row["trades_path"]).read_text(encoding="utf8") == CSV_A
    assert saved["stats"]["trades_anzahl"] == row["forensik"]["trades_anzahl"] == 2
    assert saved["stats"]["winrate_pct"] == row["forensik"]["winrate_pct"] == 50
    assert hashlib.sha256(CSV_A.encode()).hexdigest() == row["trades_sha256"] == row["forensik"]["trades_sha256"]
    assert analyzed_paths == [result.trades_path] and return_paths
    assert set(return_paths) == {result.trades_path}
    loaded = pipeline.results_from_db(materialize_pdfs=False)[0]
    assert loaded.forensik_vorhanden and not loaded.forensik_stale
    assert loaded.winrate_pct == 50 and loaded.trades_sha256 == result.trades_sha256


def test_commit_rejects_changed_analysis_input_and_rolls_back(tmp_path):
    db.init_db()
    source = tmp_path / "input.csv"
    source.write_text(CSV_A, encoding="utf8")
    db.store_scan_result(123, {"name": "previous"}, str(source), {"score": 1})
    before = db.list_catalog()
    expected = db.file_sha256(str(source))
    source.write_text(CSV_B, encoding="utf8")
    with pytest.raises(ValueError, match="Trade-SHA"):
        db.store_scan_result(123, {"name": "new", "quelle": "mql5"}, str(source),
                             {"score": 2, "trades_sha256": expected},
                             expected_trades_sha256=expected)
    assert db.list_catalog() == before
    assert Path(before[0]["trades_path"]).read_text(encoding="utf8") == CSV_A


@pytest.mark.parametrize("report_sha", [None, "different"])
def test_commit_requires_explicit_matching_finding_sha(tmp_path, report_sha):
    db.init_db()
    source = tmp_path / "input.csv"
    source.write_text(CSV_A, encoding="utf8")
    expected = db.file_sha256(str(source))
    report = {"score": 1}
    if report_sha is not None:
        report["trades_sha256"] = report_sha
    with pytest.raises(ValueError, match="Befund-SHA"):
        db.store_scan_result(123, {"name": "new"}, str(source), report,
                             expected_trades_sha256=expected)
    assert db.list_catalog() == []


@pytest.mark.parametrize("changed", [False, True])
def test_reload_rejects_missing_or_changed_snapshot(safe_scan, tmp_path, monkeypatch, changed):
    source = tmp_path / "cache.csv"
    source.write_text(CSV_A, encoding="utf8")
    monkeypatch.setattr(pipeline.exporter, "export_positions", lambda *a, **kw: (str(source), False))
    result = safe_scan._analyze_candidate_once(None, {"id": 123, "platform": "MT5"}, lambda _: None)
    assert result.forensik_vorhanden and not result.fehler
    if changed:
        Path(result.trades_path).write_text(CSV_B, encoding="utf8")
    else:
        Path(result.trades_path).unlink()
    loaded = pipeline.results_from_db(materialize_pdfs=False)[0]
    assert loaded.forensik_stale and not loaded.forensik_vorhanden
    assert loaded.score is None and loaded.max_drawdown_equity_pct is None
    assert loaded.ampel != "🟢" and "Trade-Snapshot" in loaded.fehler


def test_pipeline_rejects_snapshot_modified_before_commit(safe_scan, tmp_path, monkeypatch):
    source = tmp_path / "cache.csv"
    source.write_text(CSV_A, encoding="utf8")
    monkeypatch.setattr(pipeline.exporter, "export_positions", lambda *a, **kw: (str(source), False))
    original = db.store_scan_result

    def replace_before_commit(*args, **kwargs):
        Path(kwargs["trades_path"]).write_text(CSV_B, encoding="utf8")
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "store_scan_result", replace_before_commit)
    result = safe_scan._analyze_candidate_once(None, {"id": 123, "platform": "MT5"}, lambda _: None)
    assert "Trade-SHA" in result.fehler and not result.persisted_this_run
    assert result.ampel != "🟢" and db.list_catalog() == []


@pytest.mark.parametrize("source", [None, "", " ", True])
def test_existing_scan_update_requires_explicit_source(tmp_path, source):
    db.init_db()
    path = tmp_path / "input.csv"
    path.write_text(CSV_A, encoding="utf8")
    db.store_scan_result(123, {"name": "original", "quelle": "pelik"}, str(path), {"score": 1})
    before = db.list_catalog()
    update = {"name": "unidentified replacement"}
    if source is not None:
        update["quelle"] = source
    with pytest.raises(ValueError, match="ID-Kollision abgewehrt"):
        db.store_scan_result(123, update, str(path), {"score": 2})
    assert db.list_catalog() == before


def test_legacy_initial_scan_gets_default_source_without_mutating_argument():
    db.init_db()
    initial = {"name": "legacy initial import"}
    db.store_scan_result(123, initial)
    assert db.get_signal(123)["quelle"] == "mql5"
    assert initial == {"name": "legacy initial import"}
    db.store_scan_result(123, {"name": "explicit update", "quelle": "mql5"})
    assert db.get_signal(123)["name"] == "explicit update"


def test_concurrent_initial_scans_cannot_replace_other_source():
    db.init_db()

    def write(source):
        try:
            db.store_scan_result(123, {"name": source, "quelle": source})
            return "saved"
        except ValueError as error:
            assert "ID-Kollision abgewehrt" in str(error)
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ["mql5", "pelik"]))
    assert sorted(outcomes) == ["saved", "saved"]
    for source in ('mql5','pelik'):
        record = db.get_signal(123,quelle=source)
        assert record['name'] == record['quelle']
    with pytest.raises(db.AmbiguousSignalIdentity): db.get_signal(123)
