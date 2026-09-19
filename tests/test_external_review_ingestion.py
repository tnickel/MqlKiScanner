"""English MQL5 numeric values retain their scale through the live scan path."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import pipeline, scoring
from mqlkiscanner.mql5.signal_stats import _number, parse_detail_html


@pytest.mark.parametrize("text,expected", [
    ("1,085", 1085), ("1,403.03", 1403.03), ("1,234,567.89 USD", 1234567.89),
    ("-1,403.03 %", -1403.03), ("USD \u2212 1,403.03", -1403.03),
    ("+1,403", 1403), ("1 403.03", 1403.03),
    ("1\u00a0403.03", 1403.03), ("1\u202f403\u202f030.25", 1403030.25),
    ("1\u2009403.03", 1403.03), ("1.403", 1.403), ("0.125 %", .125),
    ("-.5", -.5), ("0", 0), ("1,085 (85.0%)", 1085),
])
def test_english_detail_numbers_preserve_sign_scale_and_decimal_dot(text, expected):
    assert _number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [
    "", "N/A", "29,8", "1,40", "12,34,567", "1.403.030", "1.403,03",
    "1,403,03", "9" * 400,
])
def test_malformed_or_other_locale_values_are_not_guessed(text):
    assert _number(text) is None


def test_separate_values_are_not_merged_when_reading_a_label_buffer():
    assert _number("5 12") == 5


HTML = (
    "<b>Trades:</b><span>1,085</span>"
    "<b>Growth:</b><span>1,403.03 %</span>"
    "<b>Gross Profit:</b><span>12,345.67 USD</span>"
    "<b>Gross Loss:</b><span>-1,234.56 USD</span>"
    "<b>Profit Factor:</b><span>1,403.03</span>"
    "<b>Weeks:</b><span>1,085</span>"
    "<b>Monthly growth:</b><span>1,005.25 %</span>"
    "<b>By Equity:</b><span>5.5 %</span>"
)


def test_detail_html_preserves_grouped_metrics():
    stats = parse_detail_html(HTML)
    assert stats["trades"] == 1085
    assert stats["growth_pct"] == pytest.approx(1403.03)
    assert stats["gross_profit"] == pytest.approx(12345.67)
    assert stats["gross_loss"] == pytest.approx(-1234.56)
    assert stats["profit_factor"] == pytest.approx(1403.03)
    assert stats["weeks"] == 1085
    assert stats["monthly_growth_pct"] == pytest.approx(1005.25)


@pytest.mark.parametrize("server", ["VTMarkets-Live2", "VTMarkets-Live 2"])
def test_detail_html_accepts_broker_server_with_optional_space(server):
    stats = parse_detail_html(
        f"<p>The provider's quotes from \"{server}\" are used for comparison.</p>")
    assert stats["broker_server"] == server


@pytest.mark.parametrize("card_weeks,expected_weeks", [(None, 1085), (52, 52)])
def test_live_pipeline_persists_detail_metrics_and_preserves_card_age(
        tmp_path, monkeypatch, card_weeks, expected_weeks):
    csv = tmp_path / "trade.csv"
    csv.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2025.12.31 00:00:00;Balance;;;;;;;;;1000\n"
        "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0;10\n",
        encoding="utf8")
    monkeypatch.setattr(pipeline.exporter, "export_positions", Mock(return_value=(str(csv), False)))
    session = SimpleNamespace(get=Mock(return_value=SimpleNamespace(text=HTML)))
    result = pipeline.ScanPipeline().analyze_candidate(
        session, {"id": 123, "wochen": card_weeks}, lambda _: None)
    assert not result.fehler
    assert result.wochen == expected_weeks
    assert result.pf == pytest.approx(1403.03)
    assert result.ertrag_monat_pct == pytest.approx(1005.25)
    stored = pipeline.results_from_db()[0]
    assert stored.wochen == expected_weeks
    assert stored.pf == result.pf
    assert stored.ertrag_monat_pct == result.ertrag_monat_pct


def test_missing_web_age_uses_csv_duration_before_zero_fallback():
    report = {"stats": {"span_weeks": 52}}
    fallback = scoring.dimension_inputs(report, {"weeks": None})["track"]
    assert fallback == scoring.dimension_inputs(report, {"weeks": 52})["track"]
    assert fallback < scoring.dimension_inputs({"stats": {}}, {"weeks": None})["track"]
