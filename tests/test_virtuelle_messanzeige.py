import pytest

from mqlkiscanner import pipeline
from mqlkiscanner.alle_signale_ui import tabellen_zeile


@pytest.mark.parametrize('reliable', [False, True])
def test_virtuelle_studie_zeigt_kursqualitaet_ohne_workflow_freigabe(reliable):
    result = pipeline.ScanResult(id=42, quelle='mql5', account_currency='USD', trades_sha256='current')
    pipeline.studie_anwenden(result, {result.signal_key: {
        'trades_sha': 'current', 'virtuell': True, 'dd_usd': 352.0,
        'cagr_jahr_pct': 12.0, 'ertrag_monat_geom_pct': 1.0,
        'report': {'verlaesslich': reliable, 'equity_dd_pct': 0.35,
                   'equity_dd_pct_raw': 0.3518,
                   'grund': 'Abdeckung 3% < 95%' if not reliable else ''}}})
    row = tabellen_zeile(result, {}, fix_ids=set())
    assert row['True-DD %'] == 0.3518
    assert row['TrueRetDD'] == pytest.approx(12 / 0.3518)
    assert row['RetDD/Monat'] == pytest.approx(1 / 0.3518)
    assert '10.000 USD virtuell' in row['Messstatus']
    if reliable:
        assert row['True-DD ≈'] is None
        assert row['TrueRetDD ≈'] is None
    else:
        assert row['True-DD ≈'] == 0.3518
        assert row['TrueRetDD ≈'] == row['TrueRetDD']
        assert 'Abdeckung 3%' in row['Messstatus']
    assert result.max_drawdown_equity_pct is None
    assert result.equity_dd_rekon_roh_pct is None
    assert result.retdd_jahr is None


def test_virtueller_nullertrag_ist_null_statt_unbekannt():
    result = pipeline.ScanResult(id=42, quelle='mql5', account_currency='USD', trades_sha256='current')
    pipeline.studie_anwenden(result, {result.signal_key: {
        'trades_sha': 'current', 'virtuell': True,
        'cagr_jahr_pct': 0.0, 'ertrag_monat_geom_pct': 0.0,
        'report': {'verlaesslich': True, 'equity_dd_pct_raw': 5.0}}})
    assert result.retdd_virtuell_jahr == 0.0
    assert result.retdd_virtuell_monat == 0.0


@pytest.mark.parametrize('virtual', [True, False])
def test_gescheiterte_studie_zeigt_grund_statt_leere_ohne_erklaerung(virtual):
    result = pipeline.ScanResult(id=42, quelle='mql5', account_currency='USD', trades_sha256='current')
    pipeline.studie_anwenden(result, {result.signal_key: {
        'trades_sha': 'current', 'virtuell': virtual,
        'report': {'status': 'skipped', 'grund': 'Zeitabbildung nicht monoton/eindeutig'}}})
    row = tabellen_zeile(result, {}, fix_ids=set())
    assert row['True-DD %'] is None
    assert row['TrueRetDD'] is None
    assert 'Zeitabbildung nicht monoton/eindeutig' in row['Messstatus']


@pytest.mark.parametrize('virtual', [True, False])
def test_freigegebene_teilmessung_nennt_fehlendes_instrument(virtual):
    result = pipeline.ScanResult(id=42, quelle='mql5', account_currency='USD', trades_sha256='current')
    pipeline.studie_anwenden(result, {result.signal_key: {
        'trades_sha': 'current', 'virtuell': virtual,
        'cagr_jahr_pct': 12.0, 'ertrag_monat_geom_pct': 1.0,
        'report': {'status': 'ok_teilmessung', 'verlaesslich': True,
                   'equity_dd_pct': 5.0, 'equity_dd_pct_raw': 5.0,
                   'teilmessung': True, 'symbole_nicht_betrachtet': ['FIXEDVOL80']}}})
    row = tabellen_zeile(result, {}, fix_ids=set())
    assert 'Teilmessung' in row['Messstatus']
    assert 'FIXEDVOL80' in row['Messstatus']
    assert 'unterschätzt' in row['Messstatus']
    assert row['True-DD %'] == 5.0
    if virtual:
        assert row['True-DD ≈'] == 5.0
        assert row['TrueRetDD ≈'] == pytest.approx(12 / 5)
        assert result.max_drawdown_equity_pct is None
    else:
        assert result.equity_dd_rekonstruiert_pct == 5.0


def test_reale_studie_nutzt_raw_fuer_schranke_und_retdd():
    result = pipeline.ScanResult(id=920001, quelle='mql5', account_currency='USD', trades_sha256='current', forensik_vorhanden=True)
    pipeline.studie_anwenden(result, {result.signal_key: {
        'trades_sha': 'current', 'virtuell': False,
        'cagr_jahr_pct': 12.0, 'ertrag_monat_geom_pct': 1.0,
        'report': {'status': 'ok', 'verlaesslich': True,
                   'equity_dd_pct': 30.0, 'equity_dd_pct_raw': 30.004}}})
    assert result.max_drawdown_equity_pct == 30.004
    assert result.retdd_jahr == pytest.approx(12 / 30.004)
    assert pipeline.ampel_for(result, {'schranke_eq_dd_pct': 30})[0] == '🔴'
