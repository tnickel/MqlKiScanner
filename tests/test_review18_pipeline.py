"""Boundary regressions: empty exports, preliminary verdicts and active criteria."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from mqlkiscanner import config, db, pipeline
from mqlkiscanner.llm import prompts
from mqlkiscanner.mql5.errors import Mql5CredentialsMissingError
from mqlkiscanner.parser import ORDERBOOK_HEADER
from test_review15_reports import live_reports as live_reports


@pytest.mark.parametrize("kind", ["header", "balance", "json"])
def test_local_export_without_closed_trades_does_not_abort_later_files(tmp_path, kind):
    empty = tmp_path / ("empty.json" if kind == "json" else "empty.csv")
    content = ";".join(ORDERBOOK_HEADER) + "\n"
    if kind == "balance":
        content += "2024.01.01 00:00:00;Balance;;;;;;;;;;1000;\n"
    elif kind == "json":
        content = "[]"
    empty.write_text(content, encoding="utf-8")
    good = config.RAW_DIR / "gold_spike_mt4_2349227_ORDERBOOK.csv"
    results = pipeline.ScanPipeline.analyze_local_files([str(empty), str(good)])
    assert len(results) == 2
    assert results[0].fehler and "keine abgeschlossenen Trades" in results[0].fehler
    assert not results[0].forensik_vorhanden and results[0].ampel != "🟢"
    assert results[1].forensik_vorhanden and not results[1].fehler


def test_live_empty_export_returns_readable_failure_and_retains_csv(tmp_path, monkeypatch):
    path = tmp_path / "empty.csv"
    path.write_text(";".join(ORDERBOOK_HEADER) + "\n", encoding="utf-8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", Mock(return_value={}))
    export = Mock(return_value=(str(path), False))
    monkeypatch.setattr(pipeline.exporter, "export_positions", export)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    result = pipeline.ScanPipeline().analyze_candidate(None, {"id": 123}, lambda _: None)
    assert export.call_count == 2
    assert "keine abgeschlossenen Trades" in result.fehler
    assert not result.forensik_vorhanden and result.ampel == "⚪"
    assert Path(result.trades_path).read_bytes() == path.read_bytes()
    loaded = pipeline.results_from_db()[0]
    assert loaded.fehler == result.fehler


@pytest.mark.parametrize("drawdown, limit, violated", [(45, 30, True), (15, 10, True), (10, 10, False)])
def test_preliminary_scan_applies_known_drawdown_before_database_reload(monkeypatch, drawdown, limit, violated):
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", Mock(return_value={
        "dd_equity_pct": drawdown,
    }))
    export = Mock(side_effect=Mql5CredentialsMissingError("No login configured"))
    monkeypatch.setattr(pipeline.exporter, "export_positions", export)
    pipe = pipeline.ScanPipeline({"schranke_eq_dd_pct": limit})
    result = pipe.analyze_candidate(None, {"id": 123, "platform": "MT4"}, lambda _: None)
    assert not result.fehler and not result.forensik_vorhanden
    assert result.schranke_verletzt is violated
    assert result.ampel == ("🔴" if violated else "⚪")
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert (result.ampel, result.schranke_verletzt) == (loaded.ampel, loaded.schranke_verletzt)
    assert export.call_count == 1


def test_return_verdict_names_the_configured_threshold():
    result = pipeline.ScanResult(id=123, forensik_vorhanden=True, stop_evidence="direct",
                                 score=2, ertrag_monat_pct=7)
    light, verdict = pipeline.ampel_for(result, {"min_ertrag_pct_monat": 8.5})
    assert light == "🟡" and "8.5 %/Monat" in verdict
    assert "< 5 %" not in verdict


def test_version_six_metric_snapshots_must_be_rechecked_before_reuse(live_reports):
    pipe, _, scan = live_reports
    result = scan()
    assert result.forensik_vorhanden
    old = db.list_catalog()[0]
    old["stats"]["forensik_version"] = 6
    old["stats"]["eq_dd_pct"] = None  # A title could hide the real risk metric.
    old["forensik"]["version"] = 6
    db.upsert_signal(result.id, name="By Equity:", platform="MT4", stats=old["stats"])
    db.store_forensik(result.id, old["forensik"])
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert not loaded.forensik_vorhanden and loaded.ampel != "🟢"
    assert pipe.run_llm([loaded], lambda _: None)["total"] == 0
    pipe.llm.chat.assert_not_called()
    assert db.list_catalog()[0]["forensik"]["version"] == 6  # Reading preserves history.


@pytest.mark.parametrize("shipped_template", [False, True])
def test_generated_summary_has_no_conflicting_fixed_limits(live_reports, shipped_template):
    pipe, _, scan = live_reports
    result = scan()
    pipe.settings.update(schranke_eq_dd_pct=3, min_ertrag_pct_monat=12)
    if shipped_template:
        source = Path(__file__).resolve().parents[1] / "config/prompts/gesamtbericht.md"
        prompts.save_prompt("gesamtbericht", source.read_text(encoding="utf-8"))
    assert pipe.run_llm([result], lambda _: None)["completed"] == 3
    sent = pipe.llm.chat.call_args_list[-1].args[0]
    assert "3 %" in sent and "12 %/Monat" in sent
    assert "EQ-DD > 30 %" not in sent and "Ertrag < 5 %/Monat" not in sent
    assert result.schranke_verletzt and result.ampel == "🔴"
