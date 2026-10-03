"""Brokeridentität für Kontraktspezifikationen kommt aus dem Provider-Feld."""
import pytest

from mqlkiscanner.mql5.signal_stats import parse_detail_html


@pytest.mark.parametrize("broker", ["RoboForex-ECN", "Bybit-Live-6", "FusionMarkets-Live"])
def test_provider_broker_hat_vorrang_vor_subscriber_brokern(broker):
    html = f'''<div class="s-top-info"><div class="s-plain-card__broker">
      <form><input name="substring_filter" value="{broker}">
      <a>{broker}</a></form></div></div>
      <div class="s-data-columns__item"><div class="s-data-columns__label">By Equity:</div>
      <div class="s-data-columns__value">10.45%</div></div>
      <div>Subscriber slippage: Tickmill-Live09 FusionMarkets-Live 3</div>'''
    stats = parse_detail_html(html)
    assert stats["broker_server"] == broker
    assert stats["dd_equity_pct"] == 10.45


def test_modern_ohne_provider_uebernimmt_keinen_subscriber_broker():
    html = '''<div class="s-data-columns__item">
      <div class="s-data-columns__label">By Equity:</div>
      <div class="s-data-columns__value">3.8%</div></div>
      <div>Subscriber slippage: Tickmill-Live09 FusionMarkets-Live 3</div>'''
    assert parse_detail_html(html)["broker_server"] is None


def test_provider_link_ohne_filter_feld_bleibt_lesbar():
    html = '<div class="s-plain-card__broker"><a>RoboForex-ECN</a></div>'
    assert parse_detail_html(html)["broker_server"] == "RoboForex-ECN"
