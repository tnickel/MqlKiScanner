"""Offline review probes; imported fixture isolates every application write."""
from pathlib import Path
from datetime import datetime, timedelta
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("review_conftest", ROOT / "tests/conftest.py")
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)
isolated_app_storage = cf.isolated_app_storage

from mqlkiscanner import db, pipeline, scoring
from mqlkiscanner.forensics import martingale, drawdown, exposure
from mqlkiscanner.models import Trade, ParsedExport, BalanceRow


def test_retdd_real_scan_path_never_calculates_values(tmp_path, monkeypatch):
    p = tmp_path / "trades.csv"
    p.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2026.01.01 00:00:00;Balance;;;;;;;;;1000\n"
        "2026.01.15 10:00:00;Buy;0.01;XAUUSD;4000;0.01;2026.01.15 12:00:00;4500;0;0;500\n"
        "2026.02.15 10:00:00;Buy;0.01;XAUUSD;4500;0.01;2026.02.15 12:00:00;4400;0;0;-100\n",
        encoding="utf-8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", lambda *_: {
        "dd_equity_pct": 20.0, "weeks": 52, "monthly_growth_pct": 8.0})
    monkeypatch.setattr(pipeline.exporter, "export_positions", lambda *a, **kw: (str(p), True))
    monkeypatch.setattr(pipeline.fx_rates, "status", lambda: {"geladen": False, "ordner": str(tmp_path)})
    pipe = pipeline.ScanPipeline({"equity_rekonstruktion": False})
    res = pipe._analyze_candidate_once(None, {"id": 90000001, "name": "Review"}, lambda _: None)
    assert res.forensik_vorhanden and not res.fehler, res.fehler
    names = ("retdd_monat", "retdd_jahr", "ertrag_monat_geom_pct", "cagr_jahr_pct")
    assert all(getattr(res, n) is None for n in names)
    reload = pipeline.results_from_db(pipe.settings)[0]
    assert all(getattr(reload, n) is None for n in names)
    payload = json.loads(pipeline._forensik_json(res))
    assert all(payload[n] is None for n in names)
    # Independent unrounded two-calendar-month geometric return:
    geom = ((1500 / 1000 * 1400 / 1500) ** .5 - 1) * 100
    cagr = ((1400 / 1000) ** 6 - 1) * 100
    print("RETDD", json.dumps({"actual": {n: getattr(res, n) for n in names},
          "expected_geom": geom, "expected_cagr": cagr,
          "expected_retdd_month": geom / 20, "expected_retdd_year": cagr / 20}))


def test_martingale_breakeven_is_incorrectly_treated_as_loss():
    a = datetime(2026, 1, 1)
    trades = [Trade(a, a + timedelta(hours=1), "Buy", .01, "XAUUSD", 4000, 4000, 0),
              Trade(a + timedelta(hours=2), a + timedelta(hours=3), "Buy", .02,
                    "XAUUSD", 4000, 4001, 2)]
    result = martingale.run(ParsedExport("", "positions", trades=trades))
    assert all(t.net >= 0 for t in trades)
    assert result["flag"] is True
    assert result["n_after_loss"] == 1
    res = pipeline.ScanResult(id=90000002, martingale_flag=result["flag"])
    color, verdict = pipeline.ampel_for(res, {})
    assert color == "🔴"
    print("BREAKEVEN", json.dumps({"net_profits": [t.net for t in trades], "actual": result,
                                  "ampel": color, "verdict": verdict}, ensure_ascii=False))


def test_monitor_red_flag_disappears_on_incomplete_database_reload():
    db.init_db()
    db.upsert_signal(90000003, name="Monitor red", platform="pelican", quelle="pelik",
        stats={"eq_dd_pct": 8.0, "monitor_trade_eq_dd_pct": 46.65,
               "forensik_ok": False, "last_fehler": "CSV download incomplete"})
    result = pipeline.results_from_db({"schranke_eq_dd_pct": 30})[0]
    assert result.monitor_trade_eq_dd_pct == 46.65
    assert result.schranke_verletzt is False
    assert result.ampel == "⚪"
    pipeline.refresh_report_verdict(result, {"schranke_eq_dd_pct": 30})
    assert result.schranke_verletzt is True
    assert result.ampel == "🔴"
    print("MONITOR_RELOAD", json.dumps({"monitor_dd": 46.65, "reload_color": "⚪",
                                       "after_same_refresh": result.ampel}, ensure_ascii=False))


def test_independent_net_drawdown_and_gold_contract(monkeypatch):
    a = datetime(2026, 1, 1)
    parsed = ParsedExport("", "positions", balances=[BalanceRow(a, 1000)], trades=[
        Trade(a + timedelta(hours=1), a + timedelta(hours=2), "Buy", 1, "XAUUSD", 4000, 3997,
              -300, -10, -5),
        Trade(a + timedelta(hours=3), a + timedelta(hours=4), "Buy", .01, "XAUUSD", 4000, 5000,
              1000)])
    monkeypatch.setattr(pipeline.fx_rates, "status", lambda: {"geladen": False})
    dd = drawdown.run(parsed)
    assert dd["trading_dd"]["dd_usd"] == 315
    assert dd["trading_dd"]["dd_pct_max_rel"] == 31.5
    assert dd["end_balance_real"] == 1685
    ex = exposure.run(parsed)
    assert ex["shock_usd"] == 1 * 100 * 50 == 5000
    assert ex["shock_pct_max"] == 500.0
    ev = scoring.evaluate({"forensics": {"drawdown": dd}}, {"eq_dd_pct": 8})
    assert ev["schranke_eq_dd_verletzt"] is True
    assert ev["schranke_dd_pct"] == 31.5
