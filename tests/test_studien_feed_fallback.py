"""Incomplete histories and time axes must reach other configured brokers."""
import pytest
from mqlkiscanner import studien_batch
from mqlkiscanner.forensics import equity_rekonstruktion


class Feeds:
    terminal_idx = 0
    terminal_herkunft = {}
    def __init__(self, n=3):
        self.n=n
        self.reset=0
    @property
    def terminal_pfad(self):
        return f'broker-{self.terminal_idx}'
    def hat_weiteren_terminal(self):
        return self.terminal_idx < self.n-1
    def wechsle_terminal(self):
        self.terminal_idx+=1
        return True, 'connected'
    def zurueck_zum_ersten_terminal(self):
        self.terminal_idx=0
        self.reset+=1
        return True, 'reset'


def setup(monkeypatch, reports):
    calls=[]
    def reko(parsed, provider, capital, *, broker=None):
        index = provider.anbieter.terminal_idx if isinstance(provider, studien_batch._AktuellerFeed) else provider.terminal_idx
        calls.append((index, hasattr(provider, 'hat_weiteren_terminal'), capital, broker))
        response=reports[index]
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(equity_rekonstruktion,'rekonstruiere',reko)
    return calls


def measured(cov, dd, valid=False, **extras):
    return dict(equity_dd_pct_raw=dd,abdeckung_pct_raw=cov,abdeckung_pct=cov,verlaesslich=valid,**extras)


def test_partial_history_retries_whole_feed_and_resets(monkeypatch):
    calls=setup(monkeypatch,[measured(50,7),measured(99,12,True),measured(100,99,True)])
    feeds=Feeds()
    result=studien_batch._rekonstruiere_mit_feed_fallback(object(),feeds,20000,'vantage')
    assert result['equity_dd_pct_raw']==12
    assert result['kursdaten_terminal']=='broker-1'
    assert calls==[(0,True,20000,'vantage'),(1,False,20000,'vantage')]
    assert feeds.terminal_idx==0 and feeds.reset==1
    assert len(result['kursdaten_versuche'])==2


def test_time_axis_failure_reaches_third_feed(monkeypatch):
    calls=setup(monkeypatch,[measured(100,3,grund='Zeitachse'),{'status':'skipped'},measured(98,13,True)])
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,Feeds(),10000,None)
    assert result['equity_dd_pct_raw']==13 and len(calls)==3


def test_complete_first_measurement_does_not_repeat(monkeypatch):
    calls=setup(monkeypatch,[measured(99,4,True)])
    feeds=Feeds()
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert result['equity_dd_pct_raw']==4 and len(calls)==1 and feeds.reset==0


def test_best_raw_coverage_survives_failed_later_feed(monkeypatch):
    setup(monkeypatch,[measured(80,30),measured(90,31),{'status':'skipped'}])
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,Feeds(),10000,None)
    assert not result['verlaesslich'] and result['equity_dd_pct_raw']==31


def test_later_failure_still_resets(monkeypatch):
    setup(monkeypatch,[measured(80,30),RuntimeError('feed failed')])
    feeds=Feeds(2)
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert result['equity_dd_pct_raw']==30
    assert result['kursdaten_terminal']=='broker-0'
    assert result['kursdaten_versuche'][1]['status']=='berechnung_fehlgeschlagen'
    assert feeds.terminal_idx==0 and feeds.reset==1


def test_reliable_flag_without_finite_drawdown_does_not_stop(monkeypatch):
    setup(monkeypatch,[measured(100,float('nan'),True),measured(99,7,True)])
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,Feeds(),10000,None)
    assert result['equity_dd_pct_raw']==7


def test_initial_error_can_recover_at_next_feed(monkeypatch):
    calls=setup(monkeypatch,[ValueError('initial failed'),measured(97,8,True)])
    feeds=Feeds(2)
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert result['equity_dd_pct_raw']==8 and len(calls)==2
    assert result['kursdaten_versuche'][0]['status']=='berechnung_fehlgeschlagen'
    assert feeds.terminal_idx==0


def test_all_errors_raise_original_after_reset(monkeypatch):
    original=ValueError('original failure')
    setup(monkeypatch,[original,RuntimeError('second failure')])
    feeds=Feeds(2)
    with pytest.raises(ValueError) as error:
        studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert error.value is original
    assert feeds.terminal_idx==0 and feeds.reset==1


def test_middle_error_does_not_hide_third_reliable_measurement(monkeypatch):
    setup(monkeypatch,[measured(99,33),RuntimeError('bad feed'),measured(96,4,True)])
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,Feeds(),10000,None)
    assert result['equity_dd_pct_raw']==4 and result['verlaesslich']
    assert len(result['kursdaten_versuche'])==3


@pytest.mark.parametrize('raises',[False,True])
def test_failed_connection_advances_to_next_feed(monkeypatch,raises):
    calls=setup(monkeypatch,[measured(80,30),None,measured(99,9,True)])
    class FailedMiddle(Feeds):
        def wechsle_terminal(self):
            self.terminal_idx+=1
            if self.terminal_idx==1:
                if raises:
                    raise RuntimeError('connection failed')
                return False,'connection failed'
            return True,'connected'
    feeds=FailedMiddle()
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert result['equity_dd_pct_raw']==9
    assert [c[0] for c in calls]==[0,2]
    assert feeds.terminal_idx==0


def test_switch_without_progress_is_bounded_and_preserves_report(monkeypatch):
    setup(monkeypatch,[measured(80,30)])
    class Stuck(Feeds):
        switches=0
        def wechsle_terminal(self):
            self.switches+=1
            raise RuntimeError('no progress')
    feeds=Stuck()
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert result['equity_dd_pct_raw']==30 and feeds.switches==1
    assert result['kursdaten_versuche'][-1]['status']=='kein_feed_fortschritt'


@pytest.mark.parametrize('raises',[False,True])
def test_reset_failure_preserves_best_report(monkeypatch,raises):
    setup(monkeypatch,[measured(80,30),measured(99,9,True)])
    class BadReset(Feeds):
        def zurueck_zum_ersten_terminal(self):
            if raises:
                raise RuntimeError('reset failed')
            return False,'reset failed'
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,BadReset(2),10000,None)
    assert result['equity_dd_pct_raw']==9
    assert result['kursdaten_versuche'][-1]['status']=='reset_fehlgeschlagen'


def test_initial_error_after_symbol_switch_resets_before_comparison(monkeypatch):
    feeds=Feeds()
    calls=[]
    def reko(parsed,provider,capital,*,broker=None):
        calls.append(feeds.terminal_idx)
        if not isinstance(provider,studien_batch._AktuellerFeed):
            feeds.terminal_idx=2
            raise RuntimeError('symbol fallback failed after switch')
        return measured(99,9,True)
    monkeypatch.setattr(equity_rekonstruktion,'rekonstruiere',reko)
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,feeds,10000,None)
    assert result['equity_dd_pct_raw']==9 and calls==[0,1]
    assert feeds.terminal_idx==0 and feeds.reset==2


def test_mixed_first_attempt_records_only_current_confirmed_symbols(monkeypatch):
    from types import SimpleNamespace
    feeds=Feeds()
    feeds.terminal_herkunft={'EURUSD':'broker-0','XAUUSD':'broker-2',
                            'GBPUSD':'stale','USDJPY':'missing'}
    setup(monkeypatch,[measured(99,9,True,symbole_mit_kursen=['EURUSD','XAUUSD','GBPUSD'])])
    parsed=SimpleNamespace(trades=[SimpleNamespace(symbol=s) for s in ['EURUSD','XAUUSD','USDJPY']])
    result=studien_batch._rekonstruiere_mit_feed_fallback(parsed,feeds,10000,None)
    assert result['kursdaten_versuche'][0]['symbol_feeds']=={
        'EURUSD':'broker-0','XAUUSD':'broker-2'}


def test_standalone_provider_without_terminal_properties(monkeypatch):
    monkeypatch.setattr(equity_rekonstruktion,'rekonstruiere',lambda *a,**kw:measured(99,8,True))
    result=studien_batch._rekonstruiere_mit_feed_fallback(None,object(),10000,None)
    assert result['equity_dd_pct_raw']==8 and result['kursdaten_terminal'] is None
