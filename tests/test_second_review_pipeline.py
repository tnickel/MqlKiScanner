"""Zweites Review: Transaktionen, Befundversionen, KI-Eingaben und Archive."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner import db, pipeline
from mqlkiscanner.analysis_version import FORENSICS_VERSION
from mqlkiscanner.llm.client import GlmClient, LlmError, LlmNoBalanceError
from mqlkiscanner.mql5.errors import Mql5CredentialsMissingError


@pytest.fixture
def live_scan(tmp_path, monkeypatch):
    csv = tmp_path / "scan.csv"
    csv.write_text(
        "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
        "2023.12.31 10:00:00;Balance;;;;;;;;;;1000;\n"
        "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.01 11:00:00;2001;0;0;1;\n"
        "2024.01.02 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.02 11:00:00;1999;0;0;-1;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        Mock(return_value={"dd_equity_pct": 5, "monthly_growth_pct": 10}))
    monkeypatch.setattr(pipeline.exporter, "export_positions", Mock(return_value=(str(csv), False)))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    db.init_db()
    return pipeline.ScanPipeline(), csv


def _old_failed_signal():
    db.upsert_signal(123, name="Old", platform="MT5", stats={
        "forensik_ok": False, "last_fehler": "alter Exportfehler",
        "forensik_version": FORENSICS_VERSION,
    })
    db.store_forensik(123, {"version": FORENSICS_VERSION, "score": 1.0,
                            "peak_exposure": {"shock_pct_max": 99999}})


def test_scan_transaction_rolls_back_even_after_forensics_write(live_scan, monkeypatch):
    pipe, csv = live_scan
    _old_failed_signal()
    db.store_trade_file(123, str(csv))
    before = db.list_catalog()
    original = db.store_forensik

    def write_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("simulierter Schreibfehler")

    write = Mock(side_effect=write_then_fail)
    monkeypatch.setattr(db, "store_forensik", write)
    result = pipe.analyze_candidate(None, {"id": 123, "name": "New"}, lambda _: None)
    assert write.call_count == 2  # Einmalige Wiederholung erreicht auch Speicherfehler.
    assert "Speichern fehlgeschlagen" in result.fehler
    assert result.ampel == "⚪"
    assert db.list_catalog() == before  # Keine Kombination aus alten/neuen Teilständen.
    assert not pipeline.results_from_db()[0].forensik_vorhanden


def test_storage_retry_commits_matching_current_result(live_scan, monkeypatch):
    pipe, _ = live_scan
    _old_failed_signal()
    original = db.store_forensik
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise sqlite3.OperationalError("vorübergehend gesperrt")
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "store_forensik", fail_once)
    result = pipe.analyze_candidate(None, {"id": 123, "name": "New"}, lambda _: None)
    assert len(calls) == 2 and not result.fehler
    loaded = pipeline.results_from_db()[0]
    assert loaded.forensik_vorhanden and not loaded.fehler
    assert loaded.score == result.score != 1.0
    assert loaded.forensik_version == FORENSICS_VERSION
    assert loaded.shock_pct_max == result.shock_pct_max


@pytest.mark.parametrize("version,shock", [(None, None), (1, 5.0), (FORENSICS_VERSION, None)])
def test_obsolete_or_incomplete_database_findings_are_not_candidates(version, shock):
    db.init_db()
    db.upsert_signal(123, platform="MT5", stats={
        "forensik_ok": True, "forensik_version": version, "ertrag_monat_pct": 10,
    })
    db.store_forensik(123, {"version": version, "score": 1,
                            "peak_exposure": {"shock_pct_max": shock}})
    loaded = pipeline.results_from_db()[0]
    assert not loaded.forensik_vorhanden and loaded.score is None
    assert loaded.ampel == "⚪" and "erneute Prüfung" in loaded.urteil


def test_missing_credentials_never_enter_browser_fallback(live_scan, monkeypatch):
    pipe, _ = live_scan
    direct = Mock(side_effect=Mql5CredentialsMissingError("Zugangsdaten fehlen"))
    browser = Mock(side_effect=AssertionError("Browser darf nicht starten"))
    monkeypatch.setattr(pipeline.exporter, "export_positions", direct)
    monkeypatch.setattr("mqlkiscanner.mql5.browser_session.export_positions_via_browser", browser)
    result = pipe.analyze_candidate(None, {"id": 123}, lambda _: None)
    assert not result.fehler and not result.forensik_vorhanden
    assert result.dd_equity_pct == 5 and direct.call_count == 1
    browser.assert_not_called()


def _response(status=200, code=None):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(
        {"error": {"code": code}} if status >= 400 else {
            "choices": [{"message": {"content": "Vollständiger Bericht"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 15},
        }
    ).encode()
    return response


@pytest.mark.parametrize("status,code", [(429, "1302"), (400, 1302), (429, None)])
def test_concurrency_limit_retries_and_recovers(monkeypatch, status, code):
    client = GlmClient("test", "test")
    monkeypatch.setattr(client, "_headers", lambda: {})
    post = Mock(side_effect=[_response(status, code), _response()])
    wait = Mock()
    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", post)
    monkeypatch.setattr("mqlkiscanner.llm.client.time.sleep", wait)
    assert client.chat("test") == "Vollständiger Bericht"
    assert post.call_count == 2 and client.usage.requests == 1
    wait.assert_called_once_with(5)


def test_exhausted_concurrency_is_not_a_balance_error(monkeypatch):
    client = GlmClient("test", "test")
    monkeypatch.setattr(client, "_headers", lambda: {})
    post = Mock(return_value=_response(429, 1302))
    wait = Mock()
    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", post)
    monkeypatch.setattr("mqlkiscanner.llm.client.time.sleep", wait)
    with pytest.raises(LlmError, match="Drosselung") as caught:
        client.chat("test")
    assert not isinstance(caught.value, LlmNoBalanceError)
    assert post.call_count == 3 and wait.call_count == 2


@pytest.mark.parametrize("status", [402, 429])
def test_real_balance_error_still_stops_immediately(monkeypatch, status):
    client = GlmClient("test", "test")
    monkeypatch.setattr(client, "_headers", lambda: {})
    post = Mock(return_value=_response(status, 1113))
    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", post)
    with pytest.raises(LlmNoBalanceError):
        client.chat("test")
    assert post.call_count == 1


@pytest.mark.parametrize("bad_kind", ["missing", "malformed", "oversized_field"])
def test_bad_csv_marks_one_signal_and_continues_with_valid_input(live_scan, tmp_path, bad_kind):
    pipe, csv = live_scan
    db.upsert_signal(123)
    db.upsert_signal(124)
    bad = tmp_path / "unusable.csv"
    if bad_kind == "malformed":
        bad.write_text("Time;Type\n2024.01.01 10:00:00;Buy\n", encoding="utf-8")
    elif bad_kind == "oversized_field":
        bad.write_text("Time;Type\n" + "x" * 140_000, encoding="utf-8")
    pipe.llm = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=0),
                               chat=Mock(return_value="Vollständiger Bericht"))
    results = [pipeline.ScanResult(id=123, forensik_vorhanden=True, trades_path=str(bad)),
               pipeline.ScanResult(id=124, forensik_vorhanden=True, trades_path=str(csv))]
    summary = pipe.run_llm(results, lambda _: None)
    assert "Trade-Export nicht lesbar" in results[0].llm_fehler
    assert not results[0].gesamtbericht and not results[1].llm_fehler
    assert results[1].gesamtbericht == "Vollständiger Bericht"
    assert pipe.llm.chat.call_count == 3
    assert summary["completed"] == 3 and summary["failed"] == 1
    assert db.get_latest_analysis(123, "gesamtbericht") is None


def test_portfolio_database_failure_remains_visible_and_archivable(monkeypatch):
    db.init_db()
    pipe = pipeline.ScanPipeline()
    pipe.llm = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=15),
                               chat=Mock(return_value="Einzigartiger Portfolio-Bericht"))
    monkeypatch.setattr(db, "store_analysis", Mock(side_effect=sqlite3.OperationalError("disk full")))
    results = [pipeline.ScanResult(id=123, forensik_vorhanden=True)]
    summary = pipe.run_portfolio(results, lambda _: None)
    assert summary["reason"] and summary["storage_error"]
    assert summary["text"] == "Einzigartiger Portfolio-Bericht"
    assert db.get_latest_analysis(0, "portfolio") is None
    path = pipe.save_run(results, {}, portfolio=summary)
    archived = json.loads(Path(path).read_text(encoding="utf-8"))
    assert archived["portfolio"] == summary
    assert archived["portfolio"]["model"] and archived["portfolio"]["created_at"]
