from datetime import datetime, timedelta
import math
import pytest
from mqlkiscanner.models import ParsedExport, Trade, BalanceRow, AccountCostRow
from mqlkiscanner import parser, portfolio_statistik as ps, engine, kursdaten, equity_studie as es, trade_data
from mqlkiscanner.forensics import drawdown, exposure, equity_rekonstruktion as er

START=datetime(2026,1,1,0,1)

def example():
    return ParsedExport('synthetic','positions', trades=[Trade(START,START+timedelta(hours=4),'Buy',.01,'XAUUSD',2000,2000,0,commission=-2)], costs=[AccountCostRow(START+timedelta(hours=2),-10,'Charge')])

def write_csv(tmp_path, rows):
    path=tmp_path/'costs.csv'
    path.write_text(';'.join(parser.POSITION_HEADER)+'\n'+'\n'.join(rows)+'\n',encoding='utf8')
    return str(path)

def test_parser_separate_bookings_preserves_identical_real_costs(tmp_path):
    path=write_csv(tmp_path,['2026.01.01 00:00:00;Commission;;;;;;;;;-0.1']*2)
    p=parser.load_export(path)
    assert len(p.costs)==2 and p.net_total==pytest.approx(-.2)
    assert p.trades==[] and p.balances==[]

@pytest.mark.parametrize('row',['bad;Charge;;;;;;;;;-1','2026.01.01 00:00:00;Charge;;;;;;;;;NaN','2026.01.01 00:00:00;Charge;0.1;;;;;;;;-1','2026.01.01 00:00:00;Charge;;;;;;;;;'])
def test_invalid_costs_stay_blocked(tmp_path,row):
    with pytest.raises(ValueError): parser.load_export(write_csv(tmp_path,[row]))

def test_drawdown_costs_are_losses_not_flows_and_not_double_commission():
    p=example(); r=drawdown.run(p,1000)
    assert r['net_total']==-12
    assert r['end_balance_real']==988
    assert r['trading_dd']['dd_usd']==12
    assert r['flows_total']==0
    assert trade_data.build_trade_payload(p)['meta']['netto_gesamt']==-12

def test_preopen_cost_once_and_external_deposit_wins():
    p=example();p.costs=[AccountCostRow(START-timedelta(seconds=30),-5,'Charge')]
    p.balances=[BalanceRow(START-timedelta(minutes=1),1000)]
    r=drawdown.run(p,10000)
    assert r['startkapital']==995
    assert r['end_balance_real']==993
    assert r['startkapital_quelle']=='csv_einzahlungen'

def test_monthly_costs_reduce_twr_and_do_not_neutralize():
    p=example();p.balances=[BalanceRow(START+timedelta(hours=1),1000)]
    assert ps._monatsserie(p,1000)['2026-01']==pytest.approx(-.6)

def test_cost_outside_trade_window_blocks_annualized_return(tmp_path):
    p=example();p.costs.append(AccountCostRow(START+timedelta(days=200),-3,'Commission'))
    assert ps._monatsserie(p,1000)=={}

def test_exposure_cost_lowers_real_account_without_fake_position():
    p=example();r=exposure.run(p,stress_move=50,kapitalbasis_usd=1000)
    assert r['peak_open_positions']==1
    # The highest relative shock follows the cost, while position count stays one.
    assert r['shock_pct_max']==pytest.approx(50/990*100,abs=.0001)
    assert r['shock_pct_peak_account']==990

@pytest.mark.parametrize('manual',[False,True])
def test_both_h1_paths_book_cost_after_last_trade_even_without_later_bars(monkeypatch,manual):
    p=example();p.costs.append(AccountCostRow(START+timedelta(days=1),-3,'Commission'))
    epoch=int(datetime(2026,1,1).timestamp())
    bars=[{'time':epoch+i*3600,'open':2000,'high':2001,'low':1999,'close':2000} for i in range(8)]
    provider=kursdaten.FakeKursDaten({'XAUUSD':bars})
    if manual:
        monkeypatch.setattr(es,'ermittle_gmt_je_symbol',lambda *_:{'offsets':{'XAUUSD':0},'befunde':[]})
        r=es.studie(p,provider,1000)
        assert r['punkte'][-1]['realisiert']==985
        assert r['punkte'][-1]['floating']==0
        assert r['kennzahlen']['equity_dd_usd']==15
    else:
        monkeypatch.setattr(er,'ermittle_gmt_offset',lambda *_:{'offset_s':0,'trefferquote':1,'verlaesslich':True})
        r=er.rekonstruiere(p,provider,1000)
        assert r['end_equity_usd']==985
        assert r['equity_dd_usd']==15

@pytest.mark.parametrize('manual',[False,True])
def test_both_h1_paths_keep_missing_symbol_net_and_costs(monkeypatch,manual):
    p=example()
    p.trades += [Trade(START,START+timedelta(hours=4),'Buy',.01,'XAUUSD',2000,2000,0) for _ in range(3)]
    p.trades.append(Trade(START,START+timedelta(hours=3),'Buy',.01,'NOQUOTE',1,2,-7))
    epoch=int(datetime(2026,1,1).timestamp())
    bars=[{'time':epoch+i*3600,'open':2000,'high':2001,'low':1999,'close':2000} for i in range(8)]
    provider=kursdaten.FakeKursDaten({'XAUUSD':bars})
    if manual:
        monkeypatch.setattr(es,'ermittle_gmt_je_symbol',lambda *_:{'offsets':{'XAUUSD':0},'befunde':[]})
        r=es.studie(p,provider,1000)
        assert r['punkte'][-1]['realisiert']==981
        assert r['kennzahlen']['verlaesslich'] is False
    else:
        monkeypatch.setattr(er,'ermittle_gmt_offset',lambda *_:{'offset_s':0,'trefferquote':1,'verlaesslich':True})
        r=er.rekonstruiere(p,provider,1000)
        assert r['end_equity_usd']==981


def test_positive_cost_correction_is_performance_not_deposit():
    p=example();p.costs=[AccountCostRow(START+timedelta(hours=2),5,'Commission')]
    r=drawdown.run(p,1000)
    assert r['flows_total']==0
    assert r['end_balance_real']==1003
    assert ps._monatsserie(p,1000)['2026-01']==pytest.approx(.3)


def test_preopen_cost_outside_window_has_explicit_rendite_blocker(tmp_path):
    path=write_csv(tmp_path,[
        '2025.12.31 23:59:00;Charge;;;;;;;;;-5',
        '2026.01.01 00:01:00;Buy;0.01;XAUUSD;2000;0.01;2026.06.01 04:01:00;2000;-2;0;100'])
    p=parser.load_export(path)
    result=ps.effizienz_kennzahlen(path,995,10)
    assert result['kontokosten_zeitfenster_unbelegt'] is True
    assert result['ertrag_monat_geom_pct'] is None
    assert result['netto_gesamt_usd']==93
    assert result['endkapital_virtuell_usd']==1093


def test_manual_ui_does_not_deduct_preopen_cost_twice(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from mqlkiscanner import equity_studie_ui as ui
    path=write_csv(tmp_path,[
        '2025.12.31 23:59:00;Charge;;;;;;;;;-5',
        '2026.01.01 00:01:00;Buy;0.01;XAUUSD;2000;0.01;2026.06.01 04:01:00;2000;-2;0;100'])
    class Provider:
        def starten(self): return True,''
        def beenden(self): pass
    monkeypatch.setattr(ui.kursdaten,'KursDaten',lambda *_:Provider())
    monkeypatch.setattr(ui.config,'load_settings',lambda:{})
    bases=[]
    def capture(parsed,provider,basis,**kwargs):
        bases.append(basis)
        return {}
    monkeypatch.setattr(ui,'studie',capture)
    ui.berechne(SimpleNamespace(id=1,trades_path=path,kapitalbasis_verwendet_usd=995),lambda *_:None)
    assert bases==[995]
