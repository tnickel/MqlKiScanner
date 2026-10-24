"""Analytic account histories for the shared DD rules; no market/terminal I/O."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from mqlkiscanner import kursdaten
from mqlkiscanner.forensics import drawdown, equity_rekonstruktion as er
from mqlkiscanner.forensics.drawdown_core import max_drawdown_aus_kurve


def test_absolute_and_relative_maxima_have_independent_anchors():
    result = max_drawdown_aus_kurve([
        (0, 1000, True, 0), (1, 600, True, 0),
        (2, 3000, True, 2400), (3, 2500, True, 0),
    ])
    assert result["dd_usd_raw"] == 500
    assert result["dd_pct_raw"] == pytest.approx(100 / 6)
    assert result["dd_pct_max_rel_raw"] == 40
    assert result["dd_usd_am_rel_max_raw"] == 400
    assert (result["dd_peak_time"], result["dd_time"]) == (2, 3)
    assert (result["dd_peak_time_max_rel"], result["dd_time_max_rel"]) == (0, 1)


def test_missing_measurements_carry_net_flows_without_creating_peaks():
    result = max_drawdown_aus_kurve([
        (0, 1000, True, 0), (1, 1100, True, 0),
        (2, 9000, False, -600), (3, None, False, 200),
        (4, 650, True, 0),
    ], verlauf=True)
    assert result["messpunkte"] == 3
    assert result["verlauf"][2:4] == [None, None]
    assert result["peak_balance_raw"] == 700
    assert result["dd_usd_raw"] == 50
    assert result["dd_pct_max_rel_raw"] == pytest.approx(50 / 700 * 100)
    assert result["dd_peak_time"] == 1


def test_equal_highs_and_equal_drawdowns_keep_first_timestamps():
    result = max_drawdown_aus_kurve([
        (0, 1000, True, 0), (1, 900, True, 0),
        (2, 1000, True, 0), (3, 900, True, 0),
    ])
    assert result["dd_time"] == result["dd_time_max_rel"] == 1
    assert result["dd_peak_time"] == result["dd_peak_time_max_rel"] == 0


def test_explicit_anchor_preserves_loss_at_first_measurement():
    points = [(1, 800, True, 0)]
    assert max_drawdown_aus_kurve(points)["dd_usd_raw"] == 0
    anchored = max_drawdown_aus_kurve(points, start=1000, start_time=0)
    assert anchored["dd_usd_raw"] == 200
    assert anchored["dd_peak_time"] == 0


@pytest.mark.parametrize("convention", [0, 100])
def test_nonpositive_capital_convention_is_explicit(convention):
    result = max_drawdown_aus_kurve([(1, -10, True, 0)], start=0,
                                    nichtpositiver_peak_pct=convention)
    assert result["dd_usd_raw"] == 10
    assert result["dd_pct_max_rel_raw"] == convention


def test_closing_groups_simultaneous_trades_and_flows():
    start = datetime(2026, 1, 1)
    closing = start + timedelta(hours=1)
    result = drawdown._max_drawdown_konto(
        [(closing, 1000), (closing, -500)],
        [(closing, -300), (closing, 100)], 1000)
    assert result["dd_usd_raw"] == 0
    assert result["end_balance"] == result["peak_balance"] == 1300


def test_deposit_raises_peak_only_through_account_value():
    start = datetime(2026, 1, 1)
    result = drawdown._max_drawdown_konto(
        [(start, -100), (start + timedelta(hours=2), -500)],
        [(start + timedelta(hours=1), 1000)], 1000)
    assert result["dd_usd_raw"] == 500
    assert result["peak_balance"] == 1900
    assert result["dd_pct_max_rel_raw"] == pytest.approx(500 / 1900 * 100)


def test_chart_carries_withdrawal_at_missing_measurement():
    underwater = drawdown.unterwasser_verlauf(
        [1000, 1100, None, 650], [0, 0, -400, 0])
    assert underwater[:3] == [0, 0, None]
    assert underwater[3] == pytest.approx(-50 / 700 * 100)


def test_account_adapter_books_costs_once_and_preserves_raw_precision():
    start = datetime(2026, 1, 1)
    export = SimpleNamespace(
        trades=[SimpleNamespace(open_time=start, close_time=start + timedelta(hours=2),
                                net=-20.123456)],
        costs=[SimpleNamespace(time=start - timedelta(seconds=1), amount=-5),
               SimpleNamespace(time=start, amount=-10)],
        balances=[SimpleNamespace(time=start, amount=1000),
                  SimpleNamespace(time=start + timedelta(hours=1), amount=1000)],
    )
    # Resolved starting equity already contains the initial deposit and -5 fee.
    result = drawdown.konto_drawdown(export, 995)
    assert result["end_balance"] == 1964.88
    assert result["peak_balance"] == 1985
    assert result["dd_usd"] == 20.12
    assert result["dd_usd_raw"] == pytest.approx(20.123456)


def test_curve_only_reconstruction_skips_dd_without_changing_curve(monkeypatch):
    start = datetime(2026, 1, 1)
    epoch = int(start.replace(tzinfo=timezone.utc).timestamp())
    bars = []
    for hour in range(26):
        close = 1990.0 if hour == 10 else 2000.0 + 7.0 * hour
        bars.append({"time": epoch + hour * 3600, "open": close,
                     "high": close + .4, "low": close - .4, "close": close})
    export = SimpleNamespace(trades=[SimpleNamespace(
        symbol="XAUUSD", direction="buy", volume=1.0,
        open_time=start + timedelta(hours=1), close_time=start + timedelta(hours=22),
        entry_price=2006.9, exit_price=2154.0, net=0.0)], balances=[], pendings=[])
    expected = er.rekonstruiere(export, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                               startkapital=10000, include_curve=True)
    assert expected["status"] == "ok"
    assert expected["equity_dd_usd"] > 5000

    def no_second_dd(*_args, **_kwargs):
        raise AssertionError("curve-only caller must own the single DD evaluation")

    monkeypatch.setattr(er, "max_drawdown_aus_kurve", no_second_dd)
    actual = er.rekonstruiere(export, kursdaten.FakeKursDaten({"XAUUSD": bars}),
                             startkapital=10000, include_curve=True, compute_dd=False)
    assert actual == {key: value for key, value in expected.items()
                      if not key.startswith("equity_dd_")}


def test_curve_only_reconstruction_requires_curve_opt_in():
    with pytest.raises(ValueError, match="include_curve"):
        er.rekonstruiere(None, None, startkapital=1000, compute_dd=False)
