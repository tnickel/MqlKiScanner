"""Generic synchronized loss exits are a hypothesis, never broker SL proof.

Synthetic trades deliberately omit prices so these tests exercise the new
behavior signature independently of existing loss-distance clustering.
Storage isolation and the HTTP guard come from tests/conftest.py.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import random

import pytest

from mqlkiscanner import ampel_matrix, db, pipeline, scoring
from mqlkiscanner.forensics import stops
from mqlkiscanner.models import ParsedExport, Trade


def _trade(close: datetime, index: int, *, profit: float = -10,
           commission: float = 0, swap: float = 0, symbol: str = "XAUUSD",
           direction: str = "Buy", sl: float | None = None,
           open_time: datetime | None = None) -> Trade:
    return Trade(open_time=open_time or close - timedelta(hours=2, minutes=index),
                 close_time=close, direction=direction, volume=0.01,
                 symbol=symbol, entry_price=None, exit_price=None,
                 profit=profit, commission=commission, swap=swap, sl=sl)


def _episodes(*, profits=(-10, -15, -20), events: int = 4,
              direction="Buy", symbol="XAUUSD", commission=0, swap=0):
    rows = []
    for event in range(events):
        started = datetime(2026, 1, 2, 12) + timedelta(days=event)
        for index, profit in enumerate(profits):
            rows.append(_trade(started + timedelta(seconds=index % 3), index,
                               profit=profit, direction=direction, symbol=symbol,
                               commission=commission, swap=swap))
    return rows


def _run(trades, *, orderbook=False):
    parsed = ParsedExport(source_path="synthetic", trades=trades,
                          source_format="mt4_orderbook" if orderbook else "positions")
    return stops.run(parsed)


def _signature(result):
    signature = result["schutzsignatur"]
    assert signature["version"] == 1
    assert signature["fenster_sekunden"] == stops.SYNC_CLOSE_SECONDS == 2
    assert signature["min_ereignisse"] == 3
    assert signature["min_tage"] == 2
    assert isinstance(signature["plausibel"], bool)
    assert len(signature["beispiele"]) <= 5
    return signature


def test_direct_orderbook_sl_remains_direct_evidence():
    trades = _episodes()
    for trade in trades:
        trade.sl = 1990
        trade.comment = "[sl]"
    result = _run(trades, orderbook=True)
    assert result["stop_evidence"] == "direct"
    assert result["positions_with_sl_pct"] == 100
    assert "BEWIESEN" in result["verdict"]


@pytest.mark.parametrize("direction", ["Buy", "Sell"])
def test_repeated_synchronized_pure_net_losses_are_plausible_not_proven(direction):
    result = _run(_episodes(direction=direction))
    signature = _signature(result)
    assert signature["status"] == "plausibel" and signature["plausibel"]
    assert signature["qualifizierte_verlustgruppen"] == 4
    assert signature["tage_mit_verlustgruppen"] == 4
    assert result["stop_evidence"] == "none"
    assert "BEWIESEN" not in result["verdict"]
    assert signature["interpretation"] and signature["grenzen"]


def test_signature_is_independent_of_csv_order():
    trades = _episodes()
    ordered = _run(trades)
    random.Random(2037).shuffle(trades)
    shuffled = _run(trades)
    assert shuffled["stop_evidence"] == ordered["stop_evidence"]
    assert shuffled["schutzsignatur"] == ordered["schutzsignatur"]


def test_broker_suffixes_are_normalized_before_grouping():
    trades = _episodes()
    for index, trade in enumerate(trades):
        trade.symbol = "XAUUSD+" if index % 3 == 1 else "XAUUSD"
    signature = _signature(_run(trades))
    assert signature["plausibel"]
    assert signature["qualifizierte_verlustgruppen"] == 4


def test_empty_history_does_not_claim_a_protection_signature():
    result = _run([])
    signature = _signature(result)
    assert signature["status"] == "nicht_beobachtet"
    assert not signature["plausibel"]
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert result["stop_evidence"] == "none"


def test_examples_are_bounded_while_all_event_counts_remain_available():
    signature = _signature(_run(_episodes(events=8)))
    assert signature["qualifizierte_verlustgruppen"] == 8
    assert signature["plausibel"]
    assert len(signature["beispiele"]) == 5


@pytest.mark.parametrize("profits", [(-20, -30, 5), (-5, 20, 30), (20, 30, 5),
                                     (-20, 0, -30), (0, 0, 0)])
def test_profitable_mixed_or_zero_exits_do_not_support_protection(profits):
    result = _run(_episodes(profits=profits))
    signature = _signature(result)
    assert not signature["plausibel"]
    assert signature["status"] == "nicht_beobachtet"
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert result["stop_evidence"] == "none"


def test_net_result_including_costs_decides_loss_classification():
    result = _run(_episodes(profits=(1, 2, 3), commission=-4, swap=-1))
    signature = _signature(result)
    assert signature["plausibel"] and signature["qualifizierte_verlustgruppen"] == 4
    assert result["stop_evidence"] == "none"
    # Negative gross profit is insufficient when the actual net is positive.
    reverse = _signature(_run(_episodes(profits=(-1, -2, -3), swap=5)))
    assert not reverse["plausibel"]
    assert reverse["qualifizierte_verlustgruppen"] == 0


@pytest.mark.parametrize("events", [1, 2])
def test_one_or_two_events_are_only_a_hint(events):
    signature = _signature(_run(_episodes(events=events)))
    assert signature["status"] == "hinweis"
    assert not signature["plausibel"]
    assert signature["qualifizierte_verlustgruppen"] == events


def test_many_exits_in_one_event_are_not_independent_repetitions():
    trades = _episodes(events=1, profits=tuple(-1 - i for i in range(20)))
    started = trades[0].close_time
    for index, trade in enumerate(trades):
        trade.close_time = started + timedelta(seconds=index % 2)
    signature = _signature(_run(trades))
    assert not signature["plausibel"]
    assert signature["qualifizierte_verlustgruppen"] == 1
    assert signature["tage_mit_verlustgruppen"] == 1


def test_repeated_groups_on_only_one_day_do_not_meet_minimum_days():
    trades = _episodes()
    for event in range(4):
        for trade in trades[event * 3:(event + 1) * 3]:
            shift = timedelta(days=event) - timedelta(minutes=10 * event)
            trade.open_time -= shift
            trade.close_time -= shift
    signature = _signature(_run(trades))
    assert signature["qualifizierte_verlustgruppen"] == 4
    assert signature["tage_mit_verlustgruppen"] == 1
    assert not signature["plausibel"]


def test_isolated_losing_trades_are_not_loss_baskets():
    result = _run(_episodes(profits=(-10,), events=5))
    signature = _signature(result)
    assert not signature["plausibel"]
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert result["stop_evidence"] == "none"


def test_duplicate_rows_cannot_create_multitrade_loss_events():
    originals = _episodes(profits=(-10,), events=4)
    trades = [deepcopy(trade) for trade in originals for _ in range(3)]
    signature = _signature(_run(trades))
    assert signature["exakte_duplikate_ignoriert"] == 8
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert not signature["plausibel"]


def test_same_symbol_hedge_closures_do_not_qualify_even_when_all_lose():
    trades = _episodes()
    for index, trade in enumerate(trades):
        if index % 3 == 1:
            trade.direction = "Sell"
    signature = _signature(_run(trades))
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert not signature["plausibel"]


def test_directions_cannot_be_split_to_hide_a_hedge_inside_whole_symbol_window():
    trades = _episodes(profits=(-10, -15, -20, -25, -30))
    for index, trade in enumerate(trades):
        trade.direction = "Sell" if index % 5 >= 3 else "Buy"
    signature = _signature(_run(trades))
    # Each side has enough losing positions, but the complete symbol exit
    # window contains a hedge, so neither side may become standalone proof.
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert not signature["plausibel"]


def test_separate_symbols_cannot_be_pooled_into_one_losing_basket():
    trades = _episodes()
    for index, trade in enumerate(trades):
        trade.symbol = ("XAUUSD", "EURUSD", "USDJPY")[index % 3]
    signature = _signature(_run(trades))
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert not signature["plausibel"]


def test_positions_must_already_overlap_before_the_first_close():
    trades = _episodes()
    for event in range(4):
        group = trades[event * 3:(event + 1) * 3]
        group[1].open_time = group[0].close_time + timedelta(milliseconds=500)
    signature = _signature(_run(trades))
    assert signature["qualifizierte_verlustgruppen"] == 0
    assert not signature["plausibel"]


def test_two_second_window_is_anchored_not_transitively_chained():
    rows = []
    for event in range(4):
        started = datetime(2026, 1, 2, 12) + timedelta(days=event)
        rows.extend([_trade(started, 0, profit=-10),
                     _trade(started + timedelta(seconds=2), 1, profit=-15),
                     _trade(started + timedelta(seconds=4), 2, profit=50)])
    signature = _signature(_run(rows))
    # The profitable trade at +4s is outside the [0,2] loss window. A
    # transitive 0->2->4 grouping would instead falsely mix all three.
    assert signature["qualifizierte_verlustgruppen"] == 4
    assert signature["plausibel"]


@pytest.mark.parametrize("offset,expected", [(2, True), (3, False)])
def test_window_boundary(offset, expected):
    rows = []
    for event in range(4):
        started = datetime(2026, 1, 2, 12) + timedelta(days=event)
        rows.extend([_trade(started, 0), _trade(started + timedelta(seconds=offset), 1)])
    assert _signature(_run(rows))["plausibel"] is expected


def test_existing_price_distance_cluster_evidence_is_preserved():
    trades = _episodes()
    for trade in trades:
        trade.entry_price = 2000
        trade.exit_price = 1990
    result = _run(trades)
    assert result["stop_evidence"] == "cluster"
    assert _signature(result)["plausibel"]


def test_plausible_signature_does_not_reduce_risk_score():
    observed = _run(_episodes())
    baseline = deepcopy(observed)
    baseline.pop("schutzsignatur")
    generic = {"stats": {"avg_win": 10, "span_weeks": 52}, "forensics": {
        "drawdown": {"trading_dd": {"dd_pct": 5}},
        "exposure": {"shock_pct_max": 10},
        "martingale": {"flag": False}, "baskets": {},
    }}
    before = deepcopy(generic)
    after = deepcopy(generic)
    before["forensics"]["stops"] = baseline
    after["forensics"]["stops"] = observed
    assert _signature(observed)["plausibel"]
    assert scoring.dimension_inputs(after) == scoring.dimension_inputs(before)
    assert scoring.evaluate(after)["score"] == scoring.evaluate(before)["score"]


@pytest.mark.parametrize("flags,expected", [
    ({}, "🟡"), ({"martingale_flag": True}, "🔴"),
    ({"schranke_verletzt": True, "dd_equity_pct": 35}, "🔴"),
    ({"forensik_vorhanden": False}, "⚪"),
])
def test_signature_never_promotes_ampel_or_stop_matrix(flags, expected):
    result = pipeline.ScanResult(id=9000321, name="Synthetic", score=5.5,
                                 ertrag_monat_pct_forensik=10, forensik_vorhanden=True,
                                 stop_evidence="none", martingale_flag=False)
    for field, value in flags.items():
        setattr(result, field, value)
    before = pipeline.ampel_for(result, {})[0]
    result.stop_befund = _run(_episodes())
    result.stop_nachweis = pipeline._stop_evidence_text(result.stop_befund)
    assert _signature(result.stop_befund)["plausibel"]
    assert before == pipeline.ampel_for(result, {})[0] == expected
    assert ampel_matrix.kriterien_matrix(result)["stop"].ampel == "⚪"
    assert "Stop bewiesen" not in pipeline.ampel_for(result, {})[1]


def test_complete_stop_finding_survives_real_csv_db_archive_and_prompt_payload(tmp_path, monkeypatch):
    trades = _episodes()
    rows = ["Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit",
            "2026.01.01 00:00:00;Balance;;;;;;;;;10000"]
    for index, trade in enumerate(trades):
        rows.append(f"{trade.open_time:%Y.%m.%d %H:%M:%S};Buy;0.01;XAUUSD;"
                    f"{2000 + index};0.01;{trade.close_time:%Y.%m.%d %H:%M:%S};"
                    f"{1999 - index};0;0;{trade.profit}")
    path = tmp_path / "9000321_positions.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", lambda *a: {
        "dd_equity_pct": 5, "weeks": 100, "monthly_growth_pct": 10,
    })
    monkeypatch.setattr(pipeline.exporter, "export_positions", lambda *a, **k: (str(path), False))
    monkeypatch.setattr(pipeline.ScanPipeline, "_kursanbieter_fuer", lambda *a: None)
    monkeypatch.setattr(pipeline.fx_rates, "status", lambda: {"geladen": False})
    result = pipeline.ScanPipeline().analyze_candidate(
        None, {"id": 9000321, "name": "Synthetic exits", "platform": "MT5"}, lambda *a: None)
    assert not result.fehler
    assert result.forensik_vorhanden and result.stop_evidence == "none"
    assert _signature(result.stop_befund)["plausibel"]
    stored = next(row for row in db.list_catalog() if row["signal_id"] == result.id)
    assert stored["forensik"]["stop_befund"] == result.stop_befund
    loaded = pipeline.results_from_db()[0]
    archive = pipeline.ScanPipeline.save_run([result], {})
    restored = pipeline.ScanResult(**json.loads(Path(archive).read_text(encoding="utf-8"))["ergebnisse"][0])
    for current in (result, loaded, restored):
        assert current.stop_evidence == "none"
        assert current.stop_befund == result.stop_befund
        assert json.loads(pipeline._forensik_json(current))["stop_befund"] == result.stop_befund


def test_legacy_results_omit_unknown_stop_finding_from_report_basis_payload():
    result = pipeline.ScanResult(id=9000321, stop_evidence="none")
    assert result.stop_befund is None
    assert "stop_befund" not in json.loads(pipeline._forensik_json(result))
