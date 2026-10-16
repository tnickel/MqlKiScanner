"""Versioned, wholly synthetic coverage for DeepSeek P1-2 / P1-3."""
import csv
import math
from pathlib import Path

import pytest

from mqlkiscanner import parser
from mqlkiscanner.models import Trade


FIXTURES = Path(__file__).parent / "fixtures" / "parser"


@pytest.mark.parametrize("as_string", [False, True])
def test_versioned_mt4_artifacts_integrate_without_private_trade_cache(as_string):
    path = FIXTURES / "mt4_export_artifacts.csv"
    parsed = parser.load_export(str(path) if as_string else path)
    assert parsed.source_format == "mt4_orderbook"
    assert len(parsed.trades) == 6
    assert len(parsed.balances) == 9
    assert len(parsed.costs) == 2
    assert len(parsed.pendings) == 1
    assert all(isinstance(t, Trade) for t in parsed.trades)
    assert all(t.symbol.casefold() not in ("profit", "summary") for t in parsed.trades)
    assert max(t.profit for t in parsed.trades) == 50
    assert math.fsum(t.profit for t in parsed.trades) == pytest.approx(65.74)
    assert math.fsum(t.commission for t in parsed.trades) == pytest.approx(-4.10)
    assert math.fsum(t.swap for t in parsed.trades) == pytest.approx(-0.72)
    assert math.fsum(t.net for t in parsed.trades) == pytest.approx(60.92)
    assert math.fsum(b.amount for b in parsed.balances) == 1090
    assert math.fsum(c.amount for c in parsed.costs) == -3


@pytest.mark.parametrize("as_string", [False, True])
def test_versioned_mt5_artifacts_preserve_exact_cash_and_trade_results(as_string):
    path = FIXTURES / "mt5_export_artifacts.csv"
    parsed = parser.load_export(str(path) if as_string else path)
    assert parsed.source_format == "positions"
    assert len(parsed.trades) == 2
    assert len(parsed.balances) == len(parsed.costs) == 1
    assert all(isinstance(t, Trade) for t in parsed.trades)
    assert all(t.symbol.casefold() != "summary" for t in parsed.trades)
    assert math.fsum(t.profit for t in parsed.trades) == 30
    assert math.fsum(t.net for t in parsed.trades) == pytest.approx(28.60)
    assert parsed.balances[0].amount == 2000
    assert parsed.costs[0].amount == -3


def test_bom_and_large_synthetic_orderbook_keep_all_real_rows(tmp_path):
    with (FIXTURES / "mt4_export_artifacts.csv").open(encoding="utf8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    trades = [row for row in rows[1:]
              if row[1] in ("Buy", "Sell") and row[3] != "profit"]
    other = [row for row in rows[1:] if row not in trades]
    path = tmp_path / "large_synthetic_orderbook.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(rows[0])
        writer.writerows(trades * 420)
        writer.writerows(other)
    parsed = parser.load_export(path)
    assert parsed.source_format == "mt4_orderbook"
    assert len(parsed.trades) == 2520
    assert len(parsed.balances) == 9
    assert parsed.duplikate_entfernt == 0  # identical rows are no identity proof
    assert all(isinstance(t, Trade) for t in parsed.trades)
    assert max(t.profit for t in parsed.trades) == 50
    assert math.fsum(t.net for t in parsed.trades) == pytest.approx(25586.40)


@pytest.mark.parametrize("filename", ["mt4_export_artifacts.csv", "mt5_export_artifacts.csv"])
def test_public_fixtures_detect_regression_in_summary_recognition(monkeypatch, filename):
    monkeypatch.setattr(parser, "_is_mt4_summary_row", lambda *_: False)
    with pytest.raises(ValueError, match="Pflichtfeld fehlt"):
        parser.load_export(FIXTURES / filename)


@pytest.mark.parametrize("filename", ["mt4_export_artifacts.csv", "mt5_export_artifacts.csv"])
def test_truncated_public_fixture_is_never_accepted(tmp_path, filename):
    text = (FIXTURES / filename).read_text(encoding="utf8")
    path = tmp_path / filename
    path.write_text(text + "2025.06.01 10:00:00;Buy;0.10;EURUSD\n", encoding="utf8")
    with pytest.raises(ValueError, match="unvollstaendiger Export"):
        parser.load_export(path)


@pytest.mark.parametrize("filename", ["mt4_export_artifacts.csv", "mt5_export_artifacts.csv"])
def test_typeless_fee_in_public_fixture_is_never_silently_skipped(tmp_path, filename):
    with (FIXTURES / filename).open(encoding="utf8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    row = [""] * len(rows[0])
    row[0] = "2025.06.01 10:00:00"
    row[9 if len(row) == 13 else 8] = "-7.50"
    path = tmp_path / filename
    with path.open("w", encoding="utf8", newline="") as fh:
        csv.writer(fh, delimiter=";").writerows([*rows, row])
    with pytest.raises(ValueError, match="Datensatz ohne Typ"):
        parser.load_export(path)
