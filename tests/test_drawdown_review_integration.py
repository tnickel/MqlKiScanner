"""Counterexamples independently verify the external review and public units."""
from datetime import datetime, timedelta
from copy import deepcopy

import pytest

from mqlkiscanner import risiko_rechner as risk
from mqlkiscanner import abonnenten_modellrechnung as model
from mqlkiscanner.models import Trade, ParsedExport, BalanceRow, AccountCostRow
from mqlkiscanner.forensics import drawdown
from scripts import kontrollscan_bericht as control


START = datetime(2026, 1, 1)


def history(pnls, times, flows=()):
    return ParsedExport('synthetic.csv', 'positions', trades=[
        Trade(START, START+timedelta(hours=hour), 'Buy', .1, 'XAUUSD', 2000, 2001, pnl)
        for pnl, hour in zip(pnls, times)], balances=[
            BalanceRow(START-timedelta(hours=1), 1000),
            *[BalanceRow(START+timedelta(hours=hour), amount) for hour, amount in flows]])


def test_deposit_only_raises_peak_through_the_account_value():
    # 1000 -> 900 -> deposit1000 =1900(new high) -> loss500 =1400.
    # Old risk/control kernels instead invented peak2000 and reported30%.
    parsed = history([-100, -500], [1, 3], [(2, 1000)])
    expected = 500 / 1900 * 100
    assert risk.closed_dd(parsed, 1000) == pytest.approx(expected)
    assert drawdown.run(parsed)['trading_dd']['dd_pct_max_rel_raw'] == pytest.approx(expected)
    calculated = control.eigene_analyse(parsed)
    assert calculated['max_dd_pct'] == pytest.approx(expected / 100)
    assert calculated['max_dd_usd'] == 500


@pytest.mark.parametrize('pnls', [[1000, -500], [-500, 1000]])
def test_same_timestamp_closes_do_not_create_an_unobserved_peak(pnls):
    # Only a net+500 event is observed; CSV row order cannot establish an interim loss.
    parsed = history(pnls, [1, 1])
    assert risk.closed_dd(parsed, 1000) == 0
    assert control.eigene_analyse(parsed)['max_dd_pct'] == 0


def test_closing_keeps_absolute_and_relative_maxima_separate():
    parsed = history([-600, 600, -150], [1, 2, 4], [(3, -800)])
    dd = drawdown.konto_drawdown(parsed, 1000)
    assert dd['dd_usd_raw'] == 600
    assert dd['dd_pct_raw'] == 60
    # Later 200 -> 50 is75% despite the smaller absolute loss of150.
    assert dd['dd_pct_max_rel_raw'] == 75
    assert risk.closed_dd(parsed, 1000) == 75


def test_new_percent_contract_and_legacy_fraction_are_converted_once():
    assert risk.closed_dd_prozent({'closed_dd_pct': 2, 'closed_dd_unit': 'percent'}) == 2
    assert risk.closed_dd_prozent({'closed_dd_pct': .02}) == 2
    assert risk.closed_dd_prozent({'closed_dd_pct': 120, 'closed_dd_unit': 'percent'}) == 120
    assert risk.closed_dd_prozent({'closed_dd_pct': None}) is None
    with pytest.raises(ValueError, match='Einheit'):
        risk.closed_dd_prozent({'closed_dd_pct': 2, 'closed_dd_unit': 'unknown'})
    with pytest.raises(ValueError, match='Einheit'):
        risk.closed_dd_prozent({'closed_dd_pct': 2, 'closed_dd_version': 2})


def test_model_kernel_keeps_pre_cost_anchor_and_skips_incomplete_points():
    prior = [AccountCostRow(START-timedelta(hours=1), -100, 'fee')]
    report = {'_curve': [(0, 900, True, 0), (1, -500, False, 0),
                         (2, 600, True, 0), (3, 1200, True, 0)]}
    model._modell_dd(report, 1000, prior)
    assert report['equity_dd_pct_raw'] == 40
    assert report['equity_dd_usd'] == 400
    assert report['min_equity_usd'] == 600
    assert not report['modell_insolvent']
    assert '_curve' not in report


def test_new_and_legacy_risk_pdf_display_identical_percent_without_double_scaling(tmp_path):
    from pypdf import PdfReader
    from test_risiko_rechner import _minimal_daten
    for kind in ('current', 'legacy'):
        data = deepcopy(_minimal_daten())
        if kind == 'current':
            data.update(closed_dd_pct=2, closed_dd_unit='percent', closed_dd_version=risk.CLOSED_DD_VERSION)
        path, _ = risk.baue_pdf(data, tmp_path/f'{kind}.pdf')
        text = ' '.join(' '.join(p.extract_text() or '' for p in PdfReader(path).pages).split())
        assert '2,00 %' in text and '2,0 % gegenüber' in text
        assert '200,00 %' not in text
        assert ('älteren Berechnung' in text) == (kind == 'legacy')


@pytest.mark.parametrize('legacy', [False, True])
def test_risk_ui_keeps_percent_unit_and_labels_legacy_results(legacy):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from test_risiko_rechner import _minimal_daten
    data = deepcopy(_minimal_daten())
    if not legacy:
        data.update(closed_dd_pct=2, closed_dd_unit='percent', closed_dd_version=risk.CLOSED_DD_VERSION)
    page = Path(__file__).resolve().parents[1] / 'app_pages' / 'risiko_rechner.py'
    app = AppTest.from_file(str(page), default_timeout=90)
    app.session_state['mrr_ergebnis'] = data
    app.run()
    assert not app.exception
    assert any('Closed-DD 2.0 % gegenüber' in item.value for item in app.error)
    assert any('älteren Berechnung' in item.value for item in app.caption) == legacy
