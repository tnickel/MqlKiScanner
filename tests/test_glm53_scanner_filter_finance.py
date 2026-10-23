"""Synthetic regressions for independently checked GLM 5.3 findings."""
from types import SimpleNamespace
import json
from unittest.mock import Mock

import pytest

from mqlkiscanner import ampel_matrix, db, fix_signale, pipeline
from mqlkiscanner.mql5 import crawler, signal_stats


def result(**overrides):
    fields = dict(id=900091, name="Synthetic", forensik_vorhanden=True,
                  ertrag_monat_geom_pct=1.0, cagr_jahr_pct=12.0,
                  equity_dd_rekonstruiert_pct=3.0, score=2.0)
    fields.update(overrides)
    return pipeline.ScanResult(**fields)


def test_mql_platform_collision_is_not_last_wins(monkeypatch):
    monkeypatch.setattr(crawler, "parse_list_html", lambda text: [
        {"id": 123, "platform": text, "wochen": 52, "abonnenten": 10}])
    session = SimpleNamespace(get=lambda url, **kw: SimpleNamespace(
        text="MT4" if "/mt4" in url else "MT5"))
    signals = crawler.crawl_lists(session, seiten_pro_liste=1)
    assert len(signals) == 2  # Both identities survive until explicit validation.
    reasons = []
    candidates = pipeline.ScanPipeline({}).build_candidates(signals, lambda _: None, reasons)
    assert candidates == []
    assert all("Kollision" in r["grund"] for r in reasons)


def test_mirror_same_identity_only_uses_first_candidate():
    entry = {"id": 123, "platform": "MT5", "wochen": 52, "abonnenten": 10}
    assert pipeline.ScanPipeline({}).build_candidates(
        [entry, dict(entry, platform="mt5")], lambda _: None) == [entry]


def test_transient_error_keeps_last_successful_partial_scan_scope():
    db.init_db()
    db.store_ampel_verlauf(123, "2026-10-15T12:00:00", "mql5", "🟢", None, "ok", {}, signal_quelle="mql5")
    failed = SimpleNamespace(id=123, ampel="⚪", source_kind="live", fehler="Timeout")
    assert fix_signale.teilscan_ziel_ids([failed], {"fix_signal_ids": []}) == {123}
    db.store_ampel_verlauf(123, "2026-10-16T12:00:00", "mql5", "🔴", None, "DD", {}, signal_quelle="mql5")
    assert fix_signale.teilscan_ziel_ids([failed], {"fix_signal_ids": []}) == set()


@pytest.mark.parametrize("currency", ["USC", "EUR", "", "USD / EUR"])
def test_native_money_is_never_implicitly_usd(currency):
    stats = signal_stats.parse_detail_html(
        f"<b>Initial Deposit:</b><span>1000 {currency}</span>"
        f"<b>Balance:</b><span>1100 {currency}</span>"
        "<b>By Equity:</b><span>12 %</span>")
    assert stats["initial_deposit_usd"] is None
    assert stats["balance_usd"] is None
    assert stats["initial_deposit_account"] == 1000
    assert stats["balance_account"] == 1100
    assert stats["dd_equity_pct"] == 12


def test_explicit_usd_remains_usable():
    stats = signal_stats.parse_detail_html("<b>Balance:</b><span>1100 USD</span>")
    assert stats["balance_usd"] == 1100
    assert stats["account_currency"] == "USD"


def test_missing_return_setting_uses_zero_in_gate_and_matrix():
    r = result()
    assert pipeline.ampel_for(r, {})[0] == "🟢"
    cell = ampel_matrix.kriterien_matrix(r, {})["ertrag"]
    assert cell.ampel == ampel_matrix.GRUEN
    assert ampel_matrix.matrix_payload(r, {})["grenzen"]["min_ertrag_pct_monat"] == 0


def test_calmar_gate_and_matrix_explicitly_disclose_h1_limits():
    r = result()
    assert "Intrabar" in pipeline.ampel_for(r, {})[1]
    assert "Intrabar" in ampel_matrix.kriterien_matrix(r, {})["retdd"].detail


def test_prompt_rule_change_invalidates_existing_report_basis(monkeypatch):
    from mqlkiscanner.llm import bausteine
    r = result()
    before = pipeline.report_basis_for(r, {})
    monkeypatch.setitem(bausteine.BAUSTEINE, "synthetic_review_rule", "changed")
    assert pipeline.report_basis_for(r, {}) != before


def test_stored_platform_collision_never_downloads_or_replaces_existing_record(monkeypatch):
    db.init_db()
    db.upsert_signal(123, name="Existing MT5", platform="MT5", quelle="mql5")
    stats = Mock(side_effect=AssertionError("No HTTP for conflicting identity"))
    monkeypatch.setattr(signal_stats, "fetch_signal_stats", stats)
    r = pipeline.ScanPipeline({})._analyze_candidate_once(
        None, {"id": 123, "platform": "MT4"}, lambda _: None)
    assert "Kollision" in r.fehler and not r.persisted_this_run
    stats.assert_not_called()
    assert db.get_signal(123)["name"] == "Existing MT5"


@pytest.mark.parametrize("currency", ["EUR", "USC", ""])
def test_non_usd_export_preserves_native_audit_and_blocks_financial_analysis(
        tmp_path, monkeypatch, currency):
    native = signal_stats.parse_detail_html(
        f"<b>Initial Deposit:</b><span>1000 {currency}</span>"
        f"<b>Balance:</b><span>1100 {currency}</span>"
        "<b>By Equity:</b><span>12 %</span>")
    csv = tmp_path / "native.csv"
    csv.write_text("synthetic export", encoding="utf8")
    monkeypatch.setattr(signal_stats, "fetch_signal_stats", lambda *_: native)
    monkeypatch.setattr(pipeline.exporter, "export_positions", lambda *a, **kw: (str(csv), False))
    fx_status = Mock(side_effect=AssertionError("No FX download before currency validation"))
    kursanbieter = Mock(side_effect=AssertionError("No terminal before currency validation"))
    monkeypatch.setattr(pipeline.fx_rates, "status", fx_status)
    monkeypatch.setattr(pipeline.ScanPipeline, "_kursanbieter_fuer", kursanbieter)
    analyze = Mock(side_effect=AssertionError("Native currency must never enter USD analysis"))
    monkeypatch.setattr(pipeline, "analyze_export", analyze)
    r = pipeline.ScanPipeline({})._analyze_candidate_once(
        None, {"id": 123, "platform": "MT5"}, lambda _: None)
    assert "Kontowährung" in r.fehler and not r.forensik_vorhanden
    assert r.dd_equity_pct == 12
    analyze.assert_not_called()
    fx_status.assert_not_called()
    kursanbieter.assert_not_called()
    stored = json.loads(db.get_signal(123)["stats_json"])
    assert stored["account_money"]["initial_deposit_account"] == 1000
    assert stored["initial_deposit_usd"] is None
    assert stored["account_currency"] == (currency or None)


def test_failed_attempt_survives_db_reload_in_partial_scan_scope(monkeypatch):
    db.init_db()
    db.upsert_signal(123, platform="MT5", quelle="mql5")
    db.store_ampel_verlauf(123, "2026-10-15T12:00:00", "mql5", "🟡", None, "ok", {}, signal_quelle="mql5")
    monkeypatch.setattr(signal_stats, "fetch_signal_stats", Mock(side_effect=TimeoutError("temporary")))
    failed = pipeline.ScanPipeline({})._analyze_candidate_once(
        None, {"id": 123, "platform": "MT5"}, lambda _: None)
    assert failed.ampel == "⚪"
    loaded = pipeline.results_from_db(materialize_pdfs=False)
    assert loaded[0].fehler and loaded[0].ampel == "⚪"
    assert fix_signale.teilscan_ziel_ids(loaded, {"fix_signal_ids": []}) == {123}


@pytest.mark.parametrize("currency", [None, "USC", "USD"])
def test_single_study_checks_currency_before_terminal(tmp_path, monkeypatch, currency):
    from mqlkiscanner import equity_studie_ui
    from mqlkiscanner.forensics import drawdown
    csv = tmp_path / "synthetic.csv"
    csv.write_text("synthetic", encoding="utf8")
    r = result(quelle="mql5", account_currency=currency, trades_path=str(csv))
    monkeypatch.setattr(equity_studie_ui.parser, "load_export",
                        lambda *a, **kw: SimpleNamespace(trades=[]))
    monkeypatch.setattr(drawdown, "run", lambda *a, **kw: {"startkapital": 1000})
    provider = Mock()
    provider.starten.return_value = (False, "synthetic connection reached")
    factory = Mock(return_value=provider)
    monkeypatch.setattr(equity_studie_ui.kursdaten, "KursDaten", factory)
    with pytest.raises((ValueError, RuntimeError), match=(
            "synthetic connection" if currency == "USD" else "Kontowährung")):
        equity_studie_ui.berechne(r, lambda *_: None)
    assert factory.call_count == int(currency == "USD")
    assert provider.starten.call_count == int(currency == "USD")


@pytest.mark.parametrize("currency", [None, "USC", "USD"])
def test_batch_checks_currency_before_terminal(monkeypatch, currency):
    from mqlkiscanner import kursdaten, studien_batch
    provider = Mock(terminal_idx=0)
    provider.starten.return_value = (True, "synthetic")
    factory = Mock(return_value=provider)
    monkeypatch.setattr(kursdaten, "KursDaten", factory)
    calculate = Mock(return_value=True)
    monkeypatch.setattr(studien_batch, "_rechne_ein_signal", calculate)
    control = dict(abbruch=False, aktuell=0, gerechnet=0, uebersprungen=0,
                   fehler=[], summary="")
    studien_batch._laufe([result(quelle="mql5", account_currency=currency)], control, {}, False)
    allowed = int(currency == "USD")
    assert factory.call_count == provider.starten.call_count == calculate.call_count == allowed
    assert control["gerechnet"] == allowed
    assert bool(control["fehler"]) is (not allowed)
    assert control["fertig"]


def test_explicit_local_demo_usd_contract_does_not_require_mql_currency():
    pipeline.require_usd_account(result(quelle="mql5", source_kind="demo"))


def test_current_parser_accepts_windows_pathlike(tmp_path):
    from mqlkiscanner import parser
    path = tmp_path / "pathlike.csv"
    path.write_text(";".join(parser.ORDERBOOK_HEADER) + "\n"
                    "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;"
                    "2024.01.01 11:00:00;2001;0;0;1;\n", encoding="utf8")
    assert len(parser.load_export(path).trades) == 1


@pytest.mark.parametrize("currency", [None, "USC", "USD"])
def test_only_proven_usd_mql_study_can_fill_display(currency):
    r = result(quelle="mql5", account_currency=currency, trades_sha256="same",
               equity_dd_rekonstruiert_pct=None)
    report = {"verlaesslich": True, "equity_dd_pct": 8}
    pipeline.studie_anwenden(r, {r.signal_key: {"trades_sha": "same", "dd_usd": 80,
                                      "report": report}})
    assert r.true_dd_usd == (80 if currency == "USD" else None)


def test_study_session_key_changes_with_native_currency():
    from mqlkiscanner.equity_studie_ui import _cache_key
    r = result(quelle="mql5", account_currency="USD", trades_sha256="same")
    usd = _cache_key(r)
    r.account_currency = "USC"
    assert _cache_key(r) != usd


def test_unknown_mql_currency_is_not_counted_as_completed_study(tmp_path):
    from mqlkiscanner import studien_batch
    csv = tmp_path / "synthetic.csv"
    csv.write_text("synthetic", encoding="utf8")
    r = result(quelle="mql5", account_currency=None, trades_sha256="same",
               trades_path=str(csv), equity_dd_rekonstruiert_pct=None)
    jobs, done = studien_batch.luecken_sammeln([r], {r.id: {
        "trades_sha": "same", "report": {"verlaesslich": True, "equity_dd_pct": 8}}},
        trades_nachladen=False)
    assert jobs == [r] and done == 0
