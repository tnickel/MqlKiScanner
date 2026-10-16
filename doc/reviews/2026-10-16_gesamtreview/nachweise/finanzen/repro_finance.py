"""Independent synthetic finance probes; no application, credentials or network.
Run: python repro_finance.py [frozen Scanner root]. Outputs only synthetic data.
"""
from pathlib import Path
from datetime import datetime as DT, timedelta, date
from unittest.mock import patch
import csv
import json
import math
import sys

HERE = Path(__file__).resolve().parent
SCANNER = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / 'scanner' / 'snapshot'
sys.path.insert(0, str(SCANNER / 'src'))
from mqlkiscanner import config, parser, stats, portfolio_statistik as ps, fx_rates, scoring, equity_studie
from mqlkiscanner.models import Trade, ParsedExport, BalanceRow, AccountCostRow
from mqlkiscanner.forensics import drawdown, equity_rekonstruktion as eq, exposure, martingale

OUT = HERE / 'synthetic'
OUT.mkdir(exist_ok=True)
(OUT / 'contract_specs.json').write_text('{}', encoding='utf-8')
RESULTS = {}

def tr(open, close, pnl, *, sym='XAUUSD', vol=.01, entry=2000., exit=2000., commission=0., swap=0.):
    return Trade(open, close, 'Buy', vol, sym, entry, exit, pnl, commission, swap)

def parsed(ts, flows=(), costs=()):
    return ParsedExport('synthetic', 'positions', list(ts), list(flows), costs=list(costs))

def save_csv(name, p, extra=()):
    path = OUT / (name + '.csv')
    fmt = parser.TIME_FMT
    rows = [list(parser.POSITION_HEADER)]
    rows += [[b.time.strftime(fmt), 'Balance', '', '', '', '', '', '', '', '', b.amount] for b in p.balances]
    rows += [[t.open_time.strftime(fmt), t.direction, t.volume, t.symbol, t.entry_price,
              t.volume, t.close_time.strftime(fmt), t.exit_price, t.commission, t.swap, t.profit] for t in p.trades]
    rows += [[c.time.strftime(fmt), c.kind, '', '', '', '', '', '', '', '', c.amount] for c in p.costs]
    rows += list(extra)
    with path.open('w', newline='', encoding='utf-8') as f:
        csv.writer(f, delimiter=';').writerows(rows)
    return str(path)

class FakeBars:
    def __init__(self, mapping): self.mapping = mapping
    def hole_h1(self, symbol, von, bis): return self.mapping.get(symbol, [])

def bars(start, closes):
    return [dict(time=eq._epoch(start+timedelta(hours=i)), open=2000., high=2200., low=1800., close=x)
            for i, x in enumerate(closes)]

def run():
    a, z = DT(2025,1,1), DT(2025,7,1)
    # Fees in rows without Type must not disappear as timestamp-only placeholders.
    p = parsed([tr(a, z, 100.)], [BalanceRow(a,1000.)])
    path = save_csv('typeless_fee', p, [[DT(2025,3,1).strftime(parser.TIME_FMT), '', '', '', '', '', '', '', '-250', '', '']])
    r = parser.load_export(path)
    RESULTS['typeless_fee'] = dict(actual_net=r.net_total, expected_error='nonempty monetary row without Type',
                                    counterfactual_net_if_charge=-150., actual_cost_count=len(r.costs))

    # Positive real capital despite nonpositive capital on hypothetical no-flow curve.
    p = parsed([tr(a,z,-200.)], [BalanceRow(a,100.),BalanceRow(DT(2025,2,1),1000.)])
    path = save_csv('deposit_valid_twr', p)
    r = ps.effizienz_kennzahlen(path,100.,10.)
    factor = 900/1100
    expected_cagr = math.expm1(math.log(factor)/((z-a).days/ps.JAHR_TAGE))*100
    RESULTS['deposit_valid_twr'] = dict(actual=r, monthly_series=ps._monatsserie(p,100.),
                                       expected_twr_total_pct=(factor-1)*100, expected_cagr_pct=expected_cagr)

    # Same-second flows have no established internal ordering; their net is zero.
    t = tr(a,z,100.)
    event = DT(2025,3,1)
    p1=parsed([t],[BalanceRow(a,100.),BalanceRow(event,-200.),BalanceRow(event,200.)])
    p2=parsed([t],[BalanceRow(a,100.),BalanceRow(event,200.),BalanceRow(event,-200.)])
    RESULTS['same_second_flows'] = dict(withdraw_first=ps._monatsserie(p1,100.),
        deposit_first=ps._monatsserie(p2,100.), expected_total_pct=100., expected_invariant=True)

    # Realized PnL is zero at an intervening deposit, but mark-to-market equity is 200.
    p=parsed([tr(a,z,200.)],[BalanceRow(a,100.),BalanceRow(DT(2025,3,1),100.)])
    path=save_csv('floating_at_flow',p)
    r=ps.effizienz_kennzahlen(path,100.,10.)
    actual_factor=math.prod(1+x/100 for x in ps._monatsserie(p,100.).values())
    # Independent unitization: preflow equity 200; afterflow equity 300; final equity 400.
    expected_factor=(200/100)*(400/300)
    RESULTS['floating_at_flow']=dict(actual=r, actual_total_pct=(actual_factor-1)*100,
        specified_equity_before_flow=200., expected_equity_twr_total_pct=(expected_factor-1)*100,
        expected_equity_cagr_pct=math.expm1(math.log(expected_factor)/((z-a).days/ps.JAHR_TAGE))*100,
        caveat='Requires observed preflow equity; closed export alone cannot establish it.')

    # Accepted partial measurement must still count observed XAUUSD losses.
    h=DT(2025,1,6,10)
    known=[tr(h,h+timedelta(hours=3),0.,vol=1.) for _ in range(4)]
    unknown=tr(h,h+timedelta(hours=3),0.,sym='MISSING',vol=1.)
    feed=FakeBars({'XAUUSD':bars(h,[1999.,1998.,2000.,2000.])})
    r=eq.rekonstruiere(parsed(known+[unknown]),feed,1000.,gmt_offset_h=0)
    c=eq.rekonstruiere(parsed(known),feed,1000.,gmt_offset_h=0)
    RESULTS['partial_loses_known_floating']=dict(actual=r, control_known_only=c,
        expected_known_component_dd_pct=80., formula='4*1lot*100 USD/unit*(2000-1998)=800 USD; 800/1000=80%')

    # A positive but much smaller realized DD allows the partial-measurement fault to green-light.
    end=h+timedelta(days=181)
    known=[tr(h,h+timedelta(hours=3),0.,vol=1.,commission=-10/3) for _ in range(3)]+[tr(h,end,1000.,vol=1.,exit=2010.)]
    missing=tr(h,h+timedelta(hours=3),0.,sym='US30',vol=1.)
    p=parsed(known+[missing],[BalanceRow(h,1000.)])
    path=save_csv('partial_false_green',p)
    b=bars(h,[1999.,1998.,2000.,2000.]+[2010.]*(181*24-2))
    for item in b:
        item['high']=item['close']; item['low']=item['close']; item['open']=item['close']
    b[0]['high']=2000.
    feed=FakeBars({'XAUUSD':b})
    r=eq.rekonstruiere(p,feed,1000.)
    d=drawdown.run(p)
    eff=ps.effizienz_kennzahlen(path,1000.,r['equity_dd_pct_raw'])
    from mqlkiscanner.pipeline import ScanResult, ampel_for
    def make_result(id, dd, efficiency, trading=None, capital=1000.):
        return ScanResult(id,name='synthetic',forensik_vorhanden=True,forensik_version=16,
            kapitalbasis_usd=capital,equity_dd_rekonstruiert_pct=dd,trading_dd_pct=trading,
            ertrag_monat_geom_pct=efficiency['ertrag_monat_geom_pct'],cagr_jahr_pct=efficiency['cagr_jahr_pct'],
            effizienz_befund=efficiency,martingale_flag=False)
    with patch.object(config,'load_known_signals',return_value={}):
        gate=ampel_for(make_result(999998,r['equity_dd_pct_raw'],eff,d['trading_dd']['dd_pct_max_rel']),
            {'schranke_eq_dd_pct':30.,'min_ertrag_pct_monat':0.,'min_calmar_jahr':3.})
    RESULTS['partial_false_green']=dict(actual=r,efficiency=eff,actual_gate=gate, expected_known_dd_pct=80.,
        expected_gate='red',scope='Public reconstruction with AUTO GMT=0; downstream Ampel with model-derived fields.')

    # The return numerator can inflate Calmar even with true observed DD <=30.
    p=parsed([tr(a,z,80.,exit=2080.)],[BalanceRow(a,100.),BalanceRow(DT(2025,3,1),100.)])
    path=save_csv('floating_loss_flow_false_green',p)
    b=bars(a,[2000.]+[1980.]*(181*24-1)+[2080.])
    for item in b:
        item['high']=item['close']; item['low']=item['close']; item['open']=item['close']
    observed=eq.rekonstruiere(p,FakeBars({'XAUUSD':b}),100.)
    eff=ps.effizienz_kennzahlen(path,100.,observed['equity_dd_pct_raw'])
    equity_factor=(80/100)*(280/180)
    equity_cagr=math.expm1(math.log(equity_factor)/((z-a).days/ps.JAHR_TAGE))*100
    with patch.object(config,'load_known_signals',return_value={}):
        gate=ampel_for(make_result(999997,20.,eff,capital=100.),{'schranke_eq_dd_pct':30.,'min_ertrag_pct_monat':0.,'min_calmar_jahr':3.})
    RESULTS['floating_loss_flow_false_green']=dict(actual=eff,actual_gate=gate,actual_reconstruction=observed,
        specified_preflow_equity=80.,specified_final_equity=280.,expected_equity_total_pct=(equity_factor-1)*100,
        expected_equity_cagr_pct=equity_cagr,expected_calmar=equity_cagr/20.,expected_gate='yellow',
        caveat='Counterexample specifies preflow mark-to-market equity, unavailable from closed CSV alone.')

    # Full study currently supplies account points to a diagnostic expecting virtual points.
    ts=[tr(h,h+timedelta(hours=1),0.),tr(h+timedelta(hours=4),h+timedelta(hours=5),0.)]
    feed=FakeBars({'XAUUSD':bars(h,[2000.]*7)})
    r=equity_studie.studie(parsed(ts,[BalanceRow(h,100.),BalanceRow(h+timedelta(hours=2),-50.)]),
        feed,100.,gmt_offset_h=0)
    RESULTS['study_double_counts_flows']=dict(actual=r,expected_final_account_equity=50.,
        expected_main_dd_pct=0.,expected_account_return_index_dd_pct=0.,expected_return_index=1.)

    # Closed DD rounded before the strict >30 gate.
    p=parsed([tr(a,a+timedelta(days=1),100.),tr(a+timedelta(days=2),a+timedelta(days=3),-330.044),
              tr(a+timedelta(days=4),z,500.)],[BalanceRow(a,1000.)])
    d=drawdown.run(p)
    risk=scoring.evaluate({'stats':{},'forensics':{'drawdown':d}}, platform={'reko_eq_dd_pct':1.})
    RESULTS['dd_rounding_gate']=dict(actual=d, gate=risk['schranke_eq_dd_verletzt'],
        expected_dd_pct=330.044/1100*100, expected_gate=True)

    # A malformed local ECB entry is accepted and marks exposure complete.
    table=fx_rates._parse_csv('Date,USD,JPY\n2025-01-06,1.1,NaN\n')
    with patch.object(fx_rates,'load',return_value=table):
        rate=fx_rates.usd_per('JPY',date(2025,1,6))
        e=exposure.run(parsed([tr(h,h+timedelta(hours=3),0.,sym='EURJPY',entry=160.,exit=160.)]),kapitalbasis_usd=1000.)
    RESULTS['nan_fx_accepted']=dict(actual_rate=rate, actual_exposure=e,
        expected='Reject NaN as unknown FX; conversion_complete=False; temporal_risk_available=False')

    # A finite adversarial spec can give negative shock and a valid completeness flag.
    badspec=dict(contract_size=-100., quote_currency='USD', stress_move=50.,cross_broker=True,source='synthetic invalid spec')
    with patch.object(exposure,'spec_for',return_value=badspec):
        e=exposure.run(parsed([tr(h,h+timedelta(hours=3),0.)]),kapitalbasis_usd=1000.)
    RESULTS['negative_contract']=dict(actual=e, expected='invalid contract must reject or mark incomplete')

    # Gross-only trade fields are intentional, but net-labelled basket evidence is not net.
    basket=[tr(h+timedelta(minutes=i),h+timedelta(hours=3),1.,vol=v,commission=-10.)
            for i,v in enumerate((.01,.02,.04))]
    m=martingale.run(parsed(basket))
    RESULTS['basket_net_is_gross']=dict(actual=m,expected_gross=3.,expected_net=-27.)
    s=stats.compute(parsed([tr(a,z,1.,commission=-10.)]))
    RESULTS['gross_vs_net_convention']=dict(actual=s,expected_net=-9.,expected_gross_winrate=100.,
        classification='Contract semantics: PF/winrate use gross Profit; net total uses commissions/swap.')

    # Controls: neutrality of withdraw, grouped closes, separate fees, missing DD and short span.
    c1=drawdown.run(parsed([tr(a,z,0.)],[BalanceRow(a,1000.),BalanceRow(DT(2025,3,1),-500.)]))
    c2=drawdown.run(parsed([tr(a,z,100.),tr(a,z,-100.)],[BalanceRow(a,1000.)]))
    c3=drawdown.run(parsed([tr(a,z,0.)],[BalanceRow(a,100.)],[AccountCostRow(DT(2025,3,1),-10.,'Charge')]))
    path=save_csv('positive_no_flows',parsed([tr(a,z,100.)],[BalanceRow(a,1000.)]))
    short=save_csv('short',parsed([tr(a,a+timedelta(days=30),100.)],[BalanceRow(a,1000.)]))
    RESULTS['controls']=dict(withdrawal_dd=c1['trading_dd'],same_second_closes_dd=c2['trading_dd'],
        separate_charge_dd=c3['trading_dd'],positive_efficiency=ps.effizienz_kennzahlen(path,1000.,10.),
        zero_dd=ps.effizienz_kennzahlen(path,1000.,0.),unknown_dd=ps.effizienz_kennzahlen(path,1000.,None),
        short_efficiency=ps.effizienz_kennzahlen(short,1000.,10.))
    RESULTS['edge_statistics']=dict(
        all_losses=stats.compute(parsed([tr(a,z,-1.),tr(a,z,-2.)])),
        all_wins=stats.compute(parsed([tr(a,z,1.),tr(a,z,2.)])),
        breakeven=stats.compute(parsed([tr(a,z,0.)])),
        before_start_cost=drawdown.run(parsed([tr(a,z,0.)],[BalanceRow(a-timedelta(days=1),100.)],
            [AccountCostRow(a-timedelta(hours=1),-10.,'Charge')])) )
    with patch.object(fx_rates,'load',return_value=fx_rates._parse_csv('Date,USD,JPY\n2025-01-03,1.2,160\n2025-01-02,1.1,150\n')):
        RESULTS['fx_controls']=dict(weekend=fx_rates.usd_per('JPY',date(2025,1,5)),
            expected_weekend_rate=1.2/160, old=fx_rates.usd_per('JPY',date(2025,1,20)))

    # End-to-end Ampel control around thresholds, no settings/DB access.
    with patch.object(config,'load_known_signals',return_value={}):
        gates={}
        for label,dd,cagr in [('exact_dd_30',30.,90.),('above_dd_30',30.0001,90.0003),
                              ('below_calmar_3',10.,29.9999),('exact_calmar_3',10.,30.),
                              ('zero_dd',0.,30.),('unknown_dd',None,30.)]:
            r=ScanResult(999999,name='synthetic',forensik_vorhanden=True,forensik_version=16,
                         kapitalbasis_usd=1000.,equity_dd_rekonstruiert_pct=dd,
                         ertrag_monat_geom_pct=math.expm1(math.log1p(cagr/100)/12)*100,cagr_jahr_pct=cagr,
                         effizienz_befund={'effizienz_status':'ok'})
            gates[label]=ampel_for(r,{'schranke_eq_dd_pct':30.,'min_ertrag_pct_monat':0.,'min_calmar_jahr':3.})
        RESULTS['ampel_threshold_controls']=gates
    # Explicit independently derived controls, plus assertions of observed faults.
    checks={
        'partial_fault_reproduced': RESULTS['partial_false_green']['actual']['equity_dd_pct_raw']==1. and RESULTS['partial_false_green']['actual_gate'][0]=='🟢',
        'partial_known_oracle_80': RESULTS['partial_loses_known_floating']['control_known_only']['equity_dd_pct_raw']==80.,
        'twr_false_green_reproduced': RESULTS['floating_loss_flow_false_green']['actual_gate'][0]=='🟢' and equity_cagr/20<3,
        'twr_independent_observed_dd_20': observed['equity_dd_pct_raw']==20. and observed['verlaesslich'],
        'study_double_flow_reproduced': RESULTS['study_double_counts_flows']['actual']['konto_studie']['kennzahlen']['konto_equity_dd_pct']==100.,
        'withdrawal_control': c1['trading_dd']['dd_pct_max_rel']==0.,
        'simultaneous_closes_control': c2['trading_dd']['dd_pct_max_rel']==0.,
        'charge_control': c3['trading_dd']['dd_pct_max_rel']==10.,
        'short_history_control': RESULTS['controls']['short_efficiency']['effizienz_status']=='historie_zu_kurz',
        'zero_dd_control': RESULTS['controls']['zero_dd']['retdd_jahr'] is None,
        'fx_weekend_control': RESULTS['fx_controls']['weekend']['rate']==1.2/160 and RESULTS['fx_controls']['old'] is None,
        'nan_dd_gate_counterevidence': scoring.dd_maximum(float('nan'),40.)==40.,
    }
    RESULTS['checks']=checks
    assert all(checks.values()), checks

if __name__=='__main__':
    import faulthandler
    faulthandler.dump_traceback_later(15, repeat=False)
    # Guard all Requests calls, even if a module unexpectedly tries to refresh FX.
    with (patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden')),
         patch.object(config,'CONTRACT_SPECS_FILE',OUT/'contract_specs.json'),
         patch.object(fx_rates,'status',return_value={'geladen':False,'ordner':'synthetic','letzte_kursdatum':None}),
         patch.object(fx_rates,'_refresh',return_value=None)):
        run()
    def clean(value):
        if isinstance(value,float) and not math.isfinite(value): return repr(value)
        if isinstance(value,dict): return {k:clean(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)): return [clean(v) for v in value]
        return value
    (HERE/'results.json').write_text(json.dumps(clean(RESULTS),ensure_ascii=False,indent=2,default=str,allow_nan=False),encoding='utf-8')
    print(json.dumps({'cases':len(RESULTS),'artifact':str(HERE/'results.json')},ensure_ascii=False))
