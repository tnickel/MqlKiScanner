"""MQL5 metric rows take precedence over signal names and other page prose."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import config, parser, pipeline
from mqlkiscanner.mql5.signal_stats import parse_detail_html


def metric(label, value, prefix="s-data-columns"):
    return (f'<div class="{prefix}__item"><div class="{prefix}__label">{label}</div>'
            f'<div class="{prefix}__value">{value}</div></div>')


def page(title="A signal"):
    return (
        f'<h1 class="s-line-card__title">{title}</h1><a>Signals</a><span>7</span>'
        + metric("Growth:", "120.5%", "s-list-info")
        + metric("Weeks:", "104", "s-list-info")
        + metric("Profit Factor:", "1.8")
        + metric("Monthly growth:", "10.5%")
        + metric("By Equity:", '<i class="red">41.2%</i> (1 234.50 USD)')
        + metric("By Balance:", "4.1% (200.00 USD)")
        + '<div id="description"><b>By Equity:</b><span>0%</span>'
          '<b>Monthly growth:</b><span>100%</span></div>'
    )


@pytest.mark.parametrize("title", ["By Equity:", "Monthly growth:", "Profit Factor:", "Weeks:"])
def test_signal_names_matching_metric_labels_cannot_replace_platform_values(title):
    original = parse_detail_html(page())
    renamed = parse_detail_html(page(title))
    assert renamed == original
    assert renamed["dd_equity_pct"] == 41.2
    assert renamed["monthly_growth_pct"] == 10.5
    assert renamed["profit_factor"] == 1.8
    assert renamed["weeks"] == 104


def test_values_stay_inside_their_metric_row_and_keep_the_first_actual_metric():
    html = (metric("Deposits:", "0.00 USD", "s-list-info")
            + '<span>Copy for 100 USD. 80% growth in 16 days.</span>'
            + metric("Growth:", "-1,403.03%", "s-list-info")
            + metric("Growth:", "999%")
            + metric("By <span>Equity:</span>", "31.5%"))
    values = parse_detail_html(html)
    assert values["deposits"] == "0.00 USD"
    assert values["growth_pct"] == -1403.03
    assert values["dd_equity_pct"] == 31.5


@pytest.mark.parametrize("real_value", [None, ""])
def test_missing_structured_value_is_never_replaced_from_unrelated_text(real_value):
    html = '<h1>By Equity:</h1><span>0%</span>'
    html += ('<div class="s-data-columns__item"><div class="s-data-columns__label">'
             'By Equity:</div>' + ('' if real_value is None else
                                  '<div class="s-data-columns__value"></div>') + '</div>')
    assert parse_detail_html(html)["dd_equity_pct"] is None


def test_plain_legacy_excerpts_keep_existing_label_parser():
    values = parse_detail_html('<b>By Equity:</b><span>31.5%</span>'
                               '<b>Monthly growth:</b><span>12.5%</span>')
    assert values["dd_equity_pct"] == 31.5
    assert values["monthly_growth_pct"] == 12.5


def test_signal_title_cannot_hide_drawdown_limit_in_pipeline(tmp_path, monkeypatch):
    path = tmp_path / "export.csv"
    rows = [";".join(parser.ORDERBOOK_HEADER),
            "2023.12.31 00:00:00;Balance;;;;;;;;;;10000;"]
    start = datetime(2024, 1, 1)
    for index in range(26):
        opened = start + timedelta(weeks=index)
        closed = opened + timedelta(hours=1)
        rows.append(f"{opened:%Y.%m.%d %H:%M:%S};Buy;0.01;XAUUSD;2000;1990;2010;"
                    f"{closed:%Y.%m.%d %H:%M:%S};2001;0;0;1;")
    path.write_text("\n".join(rows) + "\n", encoding="utf8")
    monkeypatch.setattr(config, "load_known_signals", lambda: {})
    monkeypatch.setattr(pipeline.exporter, "export_positions", Mock(return_value=(str(path), False)))
    session = SimpleNamespace(get=Mock(return_value=SimpleNamespace(text=page("By Equity:"))))
    result = pipeline.ScanPipeline().analyze_candidate(
        session, {"id": 9999001, "name": "By Equity:", "wochen": 104}, lambda _: None)
    assert not result.fehler and result.forensik_vorhanden
    assert result.dd_equity_pct == 41.2 and result.schranke_verletzt
    assert result.ampel == "🔴"
    stored = pipeline.results_from_db()[0]
    assert stored.dd_equity_pct == 41.2 and stored.schranke_verletzt
