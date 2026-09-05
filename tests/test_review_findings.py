# -*- coding: utf-8 -*-
"""Regressionen zu Code-Review-Befunden (doc/05 + ZCode F1–F19)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.forensics import exposure, martingale, stops, drawdown
from mqlkiscanner.llm.client import GlmClient, LlmError, LlmNoBalanceError
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade
from mqlkiscanner.pipeline import ScanPipeline, ScanResult
from mqlkiscanner.scoring import evaluate
from mqlkiscanner.stats import compute
from mqlkiscanner.mql5 import crawler


def _t(o, c, d, v, sym="XAUUSD", profit=0.0, sl=None, tp=None, comment=""):
    base = datetime(2024, 1, 1, 12, 0, 0)
    return Trade(
        open_time=base + timedelta(hours=o),
        close_time=base + timedelta(hours=c),
        direction=d, volume=v, symbol=sym, entry_price=2000.0, exit_price=1990.0,
        profit=profit, sl=sl, tp=tp, comment=comment,
    )


def test_z_f1_shock_uses_volume_peak_not_only_count_peak():
    trades = [_t(0, 10, "Sell", 5.0), _t(12, 14, "Sell", 0.1),
              _t(12.1, 14, "Sell", 0.1), _t(12.2, 14, "Sell", 0.1)]
    r = exposure.run(ParsedExport("x", "positions", trades=trades))
    assert r["peak_open_positions"] == 3
    assert abs(r["peak_count_shock_usd"] - 1500.0) < 1e-6
    assert abs(r["shock_usd"] - 25_000.0) < 1e-6
    assert abs(r["peak_net_lots"] + 5.0) < 1e-9


def test_z_f2_multi_symbol_uses_per_class_factors():
    trades = [_t(0, 2, "Buy", 1.0, "US30"), _t(0.1, 2, "Buy", 0.95, "NZDCAD")]
    r = exposure.run(ParsedExport("x", "positions", trades=trades))
    # 1.0 * 50 * 1 + 0.95 * 0.05 * 100000 = 50 + 4750
    assert abs(r["shock_usd"] - 4800.0) < 1e-6


def test_prev_cross_symbol_lots_do_not_cancel_shock():
    trades = [_t(0, 2, "Buy", 1.0, "XAUUSD"), _t(0.1, 2, "Sell", 1.0, "EURUSD")]
    r = exposure.run(ParsedExport("x", "positions", trades=trades))
    assert r["shock_usd"] > 0


def test_peak_count_still_reported_separately():
    trades = [_t(0, 2, "Buy", 0.01), _t(0.1, 2, "Buy", 0.01), _t(3, 5, "Buy", 1.0)]
    r = exposure.run(ParsedExport("x", "positions", trades=trades))
    assert r["peak_open_positions"] == 2
    assert abs(r["shock_usd"] - 5_000.0) < 1e-6  # Volumen-Peak = 1 Lot


def test_basket_ladder_survives_without_successors():
    trades = [
        _t(0, 5, "Buy", 0.01, profit=-1),
        _t(1, 5, "Buy", 0.02, profit=-1),
        _t(2, 5, "Buy", 0.04, profit=1),
    ]
    r = martingale.run(ParsedExport("x", "positions", trades=trades))
    assert r["basket_ladder"]["flag"] is True
    assert r["flag"] is True


def test_partial_orderbook_sl_is_not_universal_proof():
    trades = [
        _t(0, 1, "Buy", 0.1, sl=1990.0, tp=2010.0),
        _t(2, 3, "Buy", 0.1, sl=None, tp=None),
    ]
    r = stops._orderbook_evidence(ParsedExport("x", "mt4_orderbook", trades=trades))
    assert "TEILWEISE" in r["verdict"]


def test_z_f3_end_balance_does_not_double_count_start_deposit():
    trades = [_t(1, 2, "Buy", 0.1, profit=10.0)]
    bals = [BalanceRow(time=datetime(2024, 1, 1, 10), amount=1000.0)]
    dd = drawdown.run(ParsedExport("x", "positions", trades=trades, balances=bals))
    assert dd["end_balance_estimated"] == pytest.approx(
        dd["deposits_total"] + dd["withdrawals_total"] + dd["net_total"])
    assert dd["end_balance_estimated"] == pytest.approx(1010.0)


def test_z_f4_hard_barrier_uses_trading_dd_without_platform():
    fake = {
        "stats": {"avg_win": 50, "span_weeks": 104},
        "forensics": {
            "martingale": {"flag": False},
            "exposure": {"shock_usd": 100},
            "stops": {"evidence_level": 1, "positions_with_sl_tp_pct": 100, "clustered": True},
            "drawdown": {"trading_dd": {"dd_pct": 5.0, "dd_pct_max_rel": 40.0,
                                        "dd_usd": 400, "peak_balance": 10_000}},
            "baskets": {},
        },
    }
    ev = evaluate(fake, platform={"weeks": 104, "broker_risk": 3, "transparency_risk": 3})
    assert ev["schranke_eq_dd_verletzt"] is True
    assert ev["score"] < 5.0  # soft score allein wuerde Kandidat erlauben


def test_z_f5_loss_streak_from_is_series_start():
    trades = [
        Trade(open_time=datetime(2026, 1, d, 10), close_time=datetime(2026, 1, d, 11),
              direction="Buy", volume=0.1, symbol="XAUUSD",
              entry_price=1, exit_price=1, profit=-1)
        for d in (1, 2, 3)
    ]
    trades.append(Trade(
        open_time=datetime(2026, 1, 4, 10), close_time=datetime(2026, 1, 4, 11),
        direction="Buy", volume=0.1, symbol="XAUUSD",
        entry_price=1, exit_price=1, profit=5))
    s = compute(ParsedExport("x", "positions", trades=trades))
    assert s["max_loss_streak_from"].startswith("2026-01-01")
    assert s["max_loss_streak_to"].startswith("2026-01-03")


def test_z_f6_malformed_llm_json_becomes_llm_error(monkeypatch):
    monkeypatch.setattr("mqlkiscanner.llm.client.secrets_store.get_secret",
                        lambda *_a, **_k: "test-key")
    client = GlmClient("m1", "m2", base_url="https://example.test")
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "<html>nope</html>"
    resp.json.side_effect = ValueError("no json")
    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", lambda *a, **k: resp)
    with pytest.raises(LlmError, match="kein JSON"):
        client.chat("hi")


def test_z_f8_numeric_balance_code_on_402(monkeypatch):
    monkeypatch.setattr("mqlkiscanner.llm.client.secrets_store.get_secret",
                        lambda *_a, **_k: "test-key")
    client = GlmClient("m1", "m2", base_url="https://example.test")
    resp = MagicMock()
    resp.status_code = 402
    resp.text = '{"error":{"code":1113}}'
    resp.json.return_value = {"error": {"code": 1113}}
    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", lambda *a, **k: resp)
    with pytest.raises(LlmNoBalanceError):
        client.chat("hi")


def test_z_f14_crawler_num_accepts_comma_thousands():
    assert crawler._num("1,403.03") == pytest.approx(1403.03)
    assert crawler._num("1,403") == pytest.approx(1403.0)


def test_failed_rescan_does_not_resurrect_old_forensik_as_green(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.upsert_signal(7770001, name="Stale", platform="MT5",
                     stats={"eq_dd_pct": 5.0, "ertrag_monat_pct": 10.0, "last_fehler": None})
    db.store_forensik(7770001, {
        "score": 3.0, "ampel": "🟢", "martingale_flag": False,
        "stop_nachweis": "x",
        "trading_dd": {"pct": 1.0, "usd": 1.0},
        "peak_exposure": {"positionen": 1, "netto_lots": 0.1, "schock_usd": 500.0},
    })
    with db._connect() as conn:
        conn.execute(
            "UPDATE signals SET updated_at=?, stats_json=? WHERE signal_id=?",
            ("2099-01-01 12:00:00",
             json.dumps({"eq_dd_pct": 5.0, "ertrag_monat_pct": 10.0,
                         "last_fehler": "ValueError: corrupt export",
                         "forensik_ok": False}, ensure_ascii=False),
             7770001))
        conn.execute("UPDATE forensik SET updated_at=? WHERE signal_id=?",
                     ("2020-01-01 12:00:00", 7770001))
    loaded = pipeline.results_from_db()
    row = next(r for r in loaded if r.id == 7770001)
    assert row.forensik_vorhanden is False
    assert row.ampel == "⚪"


def test_a_vorpruefung_without_credentials_does_not_keep_green_forensik(
        tmp_path, monkeypatch):
    """P1-A: Export-Skip (kein Login) darf alte Forensik nicht als aktuell lassen."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "vor.db")
    db.init_db()
    sid = 7770010
    db.upsert_signal(sid, name="Alt", platform="MT5",
                     stats={"eq_dd_pct": 5.0, "ertrag_monat_pct": 10.0, "forensik_ok": True})
    db.store_forensik(sid, {
        "score": 3.0, "ampel": "🟢", "martingale_flag": False,
        "stop_nachweis": "x",
        "trading_dd": {"pct": 1.0, "usd": 1.0},
        "peak_exposure": {"positionen": 1, "netto_lots": 0.1, "schock_usd": 100.0},
    })

    class FakeSession:
        pass

    def boom_export(*_a, **_k):
        raise RuntimeError("Keine MQL5-Credentials gesetzt")

    monkeypatch.setattr("mqlkiscanner.mql5.exporter.export_positions", boom_export)
    monkeypatch.setattr(
        "mqlkiscanner.mql5.browser_session.export_positions_via_browser", boom_export)
    monkeypatch.setattr(
        "mqlkiscanner.mql5.signal_stats.fetch_signal_stats",
        lambda *_a, **_k: {"dd_equity_pct": 5.0, "dd_balance_pct": 4.0,
                           "monthly_growth_pct": 10.0, "profit_factor": 1.5, "weeks": 40})

    pipe = ScanPipeline(settings={"schranke_eq_dd_pct": 30.0})
    direct = pipe.analyze_candidate(
        FakeSession(),
        {"id": sid, "name": "Alt", "platform": "MT5", "url": "", "wochen": 40},
        log=lambda *_: None)
    assert direct.forensik_vorhanden is False
    assert direct.ampel == "⚪"

    loaded = next(r for r in pipeline.results_from_db() if r.id == sid)
    assert loaded.forensik_vorhanden is False
    assert loaded.ampel == "⚪"


def test_a_same_second_error_marks_forensik_stale(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "same.db")
    db.init_db()
    ts = "2026-09-05 12:00:00"
    db.upsert_signal(7770011, name="Same", platform="MT5",
                     stats={"eq_dd_pct": 5.0, "ertrag_monat_pct": 10.0,
                            "last_fehler": "RuntimeError: boom", "forensik_ok": False})
    db.store_forensik(7770011, {
        "score": 3.0, "ampel": "🟢", "martingale_flag": False, "stop_nachweis": "x",
        "trading_dd": {"pct": 1.0, "usd": 1.0},
    })
    with db._connect() as conn:
        conn.execute("UPDATE signals SET updated_at=? WHERE signal_id=?", (ts, 7770011))
        conn.execute("UPDATE forensik SET updated_at=? WHERE signal_id=?", (ts, 7770011))
    row = next(r for r in pipeline.results_from_db() if r.id == 7770011)
    assert row.forensik_vorhanden is False
    assert row.ampel == "⚪"


def test_c_score_uses_max_relative_drawdown():
    from datetime import datetime
    from mqlkiscanner.models import BalanceRow
    base = datetime(2024, 1, 1)
    # Start 1000; -400 → 600 (40%); +9400 → 10000; -500 → 9500 (5% am USD-Max)
    trades = [
        Trade(open_time=base, close_time=base, direction="Buy", volume=0.1,
              symbol="XAUUSD", entry_price=1, exit_price=1, profit=-400),
        Trade(open_time=base, close_time=base + timedelta(days=1), direction="Buy",
              volume=0.1, symbol="XAUUSD", entry_price=1, exit_price=1, profit=9400),
        Trade(open_time=base, close_time=base + timedelta(days=2), direction="Buy",
              volume=0.1, symbol="XAUUSD", entry_price=1, exit_price=1, profit=-500),
    ]
    bals = [BalanceRow(time=base - timedelta(hours=1), amount=1000.0)]
    dd = drawdown.run(ParsedExport("x", "positions", trades=trades, balances=bals))
    assert dd["trading_dd"]["dd_usd"] == pytest.approx(500.0)
    assert dd["trading_dd"]["dd_pct"] == pytest.approx(5.0)
    assert dd["trading_dd"]["dd_pct_max_rel"] == pytest.approx(40.0)
    fake = {"forensics": {
        "drawdown": {"trading_dd": dd["trading_dd"]},
        "martingale": {"flag": False}, "exposure": {"shock_usd": 100},
        "stops": {"evidence_level": 1, "positions_with_sl_tp_pct": 100, "clustered": True},
        "baskets": {},
    }, "stats": {"avg_win": 50, "span_weeks": 104}}
    from mqlkiscanner.scoring import dimension_inputs
    assert dimension_inputs(fake)["drawdown"] == pytest.approx(9.5)


def test_e_fx_distances_do_not_collapse_to_zero_cluster():
    base = datetime(2024, 1, 1)
    dists = [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.003, 0.005, 0.008, 0.013, 0.0199]
    fx = [
        Trade(open_time=base + timedelta(hours=i),
              close_time=base + timedelta(hours=i, minutes=30),
              direction="Buy", volume=0.1, symbol="EURUSD",
              entry_price=1.1, exit_price=1.1 - d, profit=-1)
        for i, d in enumerate(dists)
    ]
    cl = stops._distance_clustering(fx)
    assert cl["clustered"] is False
    assert cl["top_distance_level"] != 0.0
    assert "Stop-Signatur" not in cl["verdict"]


def test_d_local_roundtrip_keeps_monthly_return(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ertrag.db")
    raw = Path("data/raw/gold_spike_mt4_2349227_ORDERBOOK.csv")
    if not raw.exists():
        pytest.skip("gold spike fixture missing")
    rows = ScanPipeline.analyze_local_files([str(raw)])
    direct = next(r for r in rows if r.id == 2349227)
    assert direct.ertrag_monat_pct is not None
    loaded = next(r for r in pipeline.results_from_db() if r.id == 2349227)
    assert loaded.ertrag_monat_pct == pytest.approx(direct.ertrag_monat_pct)
    assert loaded.ampel == direct.ampel


def test_b_volume_peak_already_feeds_scoring():
    """Nachpruefung B: Score nutzt bereits Volumen-/Schock-Peak (nicht Anzahl-Peak)."""
    trades = [_t(0, 2, "Buy", 0.01), _t(0.1, 2, "Buy", 0.01), _t(3, 5, "Buy", 1.0)]
    r = exposure.run(ParsedExport("x", "positions", trades=trades))
    assert abs(r["shock_usd"] - 5000.0) < 1e-6
    fake = {"forensics": {
        "exposure": r,
        "drawdown": {"trading_dd": {"peak_balance": 10_000, "dd_pct": 5, "dd_pct_max_rel": 5}},
        "martingale": {}, "stops": {}, "baskets": {},
    }, "stats": {}}
    from mqlkiscanner.scoring import dimension_inputs
    assert dimension_inputs(fake)["margin"] == pytest.approx(8.0)


def test_self_cross_symbol_net_lots_not_zero_when_shock_high():
    trades = [_t(0, 2, "Buy", 2.0, "XAUUSD"), _t(0.1, 2, "Sell", 2.0, "EURUSD")]
    r = exposure.run(ParsedExport("x", "positions", trades=trades))
    assert r["shock_usd"] > 1000
    assert abs(r["peak_net_lots_signed_sum"]) < 1e-9
    assert abs(r["peak_net_lots"]) == pytest.approx(2.0)


def test_self_zero_start_capital_still_has_relative_dd():
    trades = [_t(0, 1, "Buy", 0.1, profit=-50)]
    dd = drawdown.run(ParsedExport("x", "positions", trades=trades, balances=[]))
    assert dd["trading_dd"]["dd_usd"] == pytest.approx(50.0)
    assert dd["trading_dd"]["dd_pct_max_rel"] == pytest.approx(100.0)


def test_self_dd_zero_is_valid_for_barrier():
    """dd_pct_max_rel=0 darf nicht durch `or` auf dd_pct fallen."""
    fake = {"forensics": {
        "drawdown": {"trading_dd": {"dd_pct": 40.0, "dd_pct_max_rel": 0.0}},
        "martingale": {"flag": False}, "exposure": {"shock_usd": 1},
        "stops": {"verdict": "x"}, "baskets": {},
    }, "stats": {}}
    ev = evaluate(fake)
    assert ev["schranke_eq_dd_verletzt"] is False
    assert ev["schranke_dd_pct"] == 0.0


def test_failed_llm_does_not_recount_old_texts(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "llm.db")
    db.init_db()
    db.upsert_signal(7770002, name="LLM", platform="MT5")

    class Boom:
        has_key = True
        usage = type("U", (), {"total_tokens": 0})()
        last_call = {}

        def chat(self, *a, **k):
            raise LlmError("boom")

    pipe = ScanPipeline()
    pipe.llm = Boom()
    r = ScanResult(id=7770002, name="LLM", forensik_vorhanden=True,
                   trade_analyse="ALT TRADE", risiko_analyse="ALT RISIKO")
    summary = pipe.run_llm([r], pipeline.StepLog())
    assert summary["completed"] == 0
    assert summary["failed"] == 1


def test_local_forensik_roundtrip_keeps_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "local.db")
    raw = Path("data/raw/goldwave_2339082_positions.csv")
    if not raw.exists():
        pytest.skip("goldwave fixture missing")
    rows = ScanPipeline.analyze_local_files([str(raw)])
    assert rows and rows[0].forensik_vorhanden
    direct = rows[0]
    loaded = next(r for r in pipeline.results_from_db() if r.id == direct.id)
    assert loaded.trading_dd_pct == pytest.approx(direct.trading_dd_pct, abs=0.05)
