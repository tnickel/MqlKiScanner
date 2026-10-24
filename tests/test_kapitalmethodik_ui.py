"""Shared capital provenance across local statistics, studies and risk UI."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import pytest

from mqlkiscanner import alle_signale_ui, equity_studie_ui, katalog, kursdaten, pipeline


def _decision(source='modell_lot_pnl'):
    return {'quelle': source, 'modell': True, 'kapital': 2500,
            'unsicherheit': 'Nur begrenzte Volumenhistorie', 'beleg': {'trades_sha256': 'frozen'}}


def test_overview_discloses_actual_estimate_and_separate_saved_study_basis():
    result = pipeline.ScanResult(id=123, quelle='mql5', account_currency='USD')
    result.true_dd_basis_virtuell = True
    result.true_dd_kapitalbasis_details = _decision('modell_lots_kalibriert')
    result.true_dd_kapitalbasis_quelle = 'modell_lots_kalibriert'
    result.true_dd_kapitalbasis_usd = 5000
    stats = {'kapitalbasis_ok': True, 'kapitalbasis_usd': 2500,
             'kapitalbasis_quelle': 'modell_lot_pnl', 'kapitalbasis_details': _decision(),
             'kapitalbasis_modell': True}
    original = deepcopy(stats)
    row = alle_signale_ui.tabellen_zeile(result, stats)
    assert row['Basis'] == 'Lot/PnL'
    assert row['Statistikbasis USD'] == 2500
    assert row['Kapitalunsicherheit'] == 'Nur begrenzte Volumenhistorie'
    assert row['Studienkapital USD'] == 5000
    assert 'Lotschaetzung' in row['Studienbasis']
    assert '10.000' not in row['Messstatus']
    assert stats == original


def test_stale_study_retdd_uses_the_return_bound_to_that_study():
    result = pipeline.ScanResult(id=124, quelle='mql5', account_currency='USD')
    result.studie_anzeige_dd_pct = 10
    result.true_dd_cagr_jahr_pct = 25
    result.true_dd_ertrag_monat_geom_pct = 2
    row = alle_signale_ui.tabellen_zeile(result, {
        'dauer_monate': 6, 'cagr_jahr_pct': 1000, 'ertrag_monat_geom_pct': 80,
        'kapitalbasis_usd': 10000, 'kapitalbasis_modell': True})
    assert row['TrueRetDD'] == 2.5
    assert row['RetDD/Monat'] == .2


def test_stale_study_does_not_mix_new_model_return_with_unbound_real_dd():
    result = pipeline.ScanResult(id=125, quelle='mql5', account_currency='USD')
    result.studie_anzeige_dd_pct = 10
    row = alle_signale_ui.tabellen_zeile(result, {
        'dauer_monate': 6, 'cagr_jahr_pct': 1000, 'ertrag_monat_geom_pct': 80,
        'kapitalbasis_usd': 10000, 'kapitalbasis_modell': True})
    assert row['TrueRetDD'] is None and row['RetDD/Monat'] is None


@pytest.mark.parametrize('source, expected', [('signalseite_initial_deposit', 890),
                                            ('virtuelle_annahme', 9990)])
def test_single_study_resolves_costs_and_withdrawals_once_without_dropping_flows(
        tmp_path, monkeypatch, source, expected):
    path = tmp_path / 'local.csv'
    path.write_text(
        'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'
        '2026.01.01 00:00:00;Balance;;;;;;;;;-100\n'
        '2026.01.01 00:01:00;Commission;;;;;;;;;-10\n'
        '2026.01.01 00:02:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.01 04:00:00;2020;0;0;20\n'
        '2026.01.01 02:00:00;Balance;;;;;;;;;-20\n', encoding='utf8')
    result = pipeline.ScanResult(id=126, quelle='mql5', account_currency='USD', trades_path=str(path),
        trades_sha256=sha256(path.read_bytes()).hexdigest(), kapitalbasis_verwendet_usd=890,
        kapitalbasis_verwendet_quelle=source)
    monkeypatch.setattr(katalog, 'metrics_stats', lambda _: {})
    provider = SimpleNamespace(starten=lambda: (True, ''), beenden=lambda: None)
    monkeypatch.setattr(kursdaten, 'KursDaten', lambda _: provider)
    captured = {}

    def study(parsed, provider, capital, **kwargs):
        captured.update(capital=capital, flows=[row.amount for row in parsed.balances],
                        costs=[row.amount for row in parsed.costs])
        return {'status': 'ok', 'kennzahlen': {'startkapital': capital}}

    monkeypatch.setattr(equity_studie_ui, 'studie', study)
    outcome = equity_studie_ui._berechne_exklusiv(result, lambda *_: None)
    assert captured == {'capital': expected, 'flows': [-100, -20], 'costs': [-10]}
    assert outcome['meta']['kapitalbasis_modell'] is (source == 'virtuelle_annahme')
    assert outcome['meta']['kapitalbasis_details']['beleg']['trades_sha256'] == result.trades_sha256
    if source == 'virtuelle_annahme':
        assert 'Modellkurve' in outcome['methodik'] and 'vorhandenen Kapitalflüssen' in outcome['methodik']
        assert 'reale Kontokurve' not in outcome['methodik']


def test_single_study_cache_separates_changed_capital_evidence():
    result = pipeline.ScanResult(id=127, quelle='mql5', account_currency='USD', trades_sha256='same')
    first = equity_studie_ui._cache_key(result)
    result.kapitalbasis_befund = _decision()
    assert equity_studie_ui._cache_key(result) != first


def test_single_study_cache_separates_changed_verified_calibration(monkeypatch):
    proof = {'status': 'geprueft', 'sha256': 'first', 'datei_sha256': 'file-first'}
    monkeypatch.setattr(equity_studie_ui.kapitalbasis, 'lade_kalibrierung_mit_beleg',
                        lambda: ({}, dict(proof)))
    result = pipeline.ScanResult(id=128, quelle='mql5', account_currency='USD', trades_sha256='same')
    first = equity_studie_ui._cache_key(result)
    proof.update(sha256='second', datei_sha256='file-second')
    assert equity_studie_ui._cache_key(result) != first
