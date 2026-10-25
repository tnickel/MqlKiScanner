import pytest
from mqlkiscanner.pipeline import ScanResult, studie_anwenden
from mqlkiscanner.alle_signale_ui import tabellen_zeile

@pytest.mark.parametrize('reliable,partial',[(True,False),(False,False),(True,True)])
def test_fresh_independent_real_study_visible_while_engine_stays_stale(reliable,partial):
    r=ScanResult(id=7,quelle='mql5',name='generic',platform='mt5',account_currency='USD',forensik_stale=True,trades_sha256='abc',ampel='⚪')
    s={r.signal_key:{'trades_sha':'abc','virtuell':False,'basislos':False,'dd_usd':100,'report':{'equity_dd_pct_raw':10,'verlaesslich':reliable,'teilmessung':partial,'kapitalbasis_usd':1000,'startkapital_quelle':'csv_einzahlungen'}}}
    studie_anwenden(r,s)
    r.refresh_efficiency()
    assert r.forensik_stale and r.ampel=='⚪'
    assert r.max_drawdown_equity_pct is None
    assert r.equity_dd_rekonstruiert_pct is None
    assert r.true_retdd_jahr is None
    row=tabellen_zeile(r,{'ertrag_monat_geom_pct':5,'cagr_jahr_pct':60,'dauer_monate':12,'kapitalbasis_usd':1000,'kapitalbasis_modell':False},fix_ids=set())
    assert row['True-DD %']==10 and row['TrueRetDD']==6 and row['RetDD/Monat']==.5
    assert (row['True-DD ≈'] is not None)==(partial or not reliable)
    assert 'Workflow-Forensik veraltet' in row['Messstatus']

@pytest.mark.parametrize('sha',['different',''])
def test_missing_or_mismatched_sha_does_not_display_stale_real_study(sha):
    r=ScanResult(id=7,quelle='mql5',name='generic',platform='mt5',account_currency='USD',forensik_stale=True,trades_sha256='abc')
    studie_anwenden(r,{r.signal_key:{'trades_sha':sha,'report':{'equity_dd_pct':10,'verlaesslich':True}}})
    assert r.studie_anzeige_dd_pct is None


def test_short_history_independent_study_has_dd_but_no_ratio():
    r=ScanResult(id=7,quelle='mql5',name='generic',platform='mt5',account_currency='USD',forensik_stale=True,trades_sha256='abc')
    studie_anwenden(r,{r.signal_key:{'trades_sha':'abc','report':{'equity_dd_pct':10,'verlaesslich':True}}})
    row=tabellen_zeile(r,{'ertrag_monat_geom_pct':5,'cagr_jahr_pct':60,'dauer_monate':2},fix_ids=set())
    assert row['True-DD %']==10 and row['TrueRetDD'] is None


@pytest.mark.parametrize('stats_capital', [None, 2000])
def test_independent_study_cannot_mix_an_unproven_or_different_return_basis(stats_capital):
    r=ScanResult(id=7,quelle='mql5',platform='mt5',account_currency='USD',forensik_stale=True,trades_sha256='abc')
    studie_anwenden(r,{r.signal_key:{'trades_sha':'abc','report':{
        'equity_dd_pct':10,'verlaesslich':True,'kapitalbasis_usd':1000,
        'startkapital_quelle':'csv_einzahlungen'}}})
    row=tabellen_zeile(r,{'ertrag_monat_geom_pct':5,'cagr_jahr_pct':60,'dauer_monate':12,
                         'kapitalbasis_usd':stats_capital,'kapitalbasis_modell':False},fix_ids=set())
    assert row['True-DD %']==10
    assert row['TrueRetDD'] is None and row['RetDD/Monat'] is None
