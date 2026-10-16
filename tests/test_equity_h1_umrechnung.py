"""H1-Umrechnung nutzt nur synchrone belegte Kurse, ohne MT5/DB."""
import datetime as dt
from types import SimpleNamespace

import pytest

from mqlkiscanner.kursdaten import FakeKursDaten
from mqlkiscanner.forensics import equity_rekonstruktion as er


START = dt.datetime(2026, 1, 5)
EPOCH = int(START.replace(tzinfo=dt.timezone.utc).timestamp())


def bars(values):
    return [dict(time=EPOCH+i*3600, open=v, close=v,
                 high=max(7.0, v), low=min(3.0, v))
            for i, v in enumerate(values) if v is not None]


def run(monkeypatch, symbol, prices, *, fxprices=None, feed=True, wrong_feed=False):
    monkeypatch.setattr(er.fx_rates, 'usd_per', lambda *_: None)
    resolve = er._resolve_symbol
    monkeypatch.setattr(er, '_resolve_symbol', lambda s, broker=None:
        dict(factor=10.0, quote='BCH') if s=='ETHBCH' else
        dict(factor=1.0, quote='ETH') if s=='BTCETH' else
        dict(factor=100000.0, quote='CNH') if s=='EURCNH' else resolve(s, broker))
    trade=SimpleNamespace(symbol=symbol, direction='buy', volume=0.01,
        open_time=START+dt.timedelta(minutes=10),
        close_time=START+dt.timedelta(hours=4),
        entry_price=7.0, exit_price=7.0, net=0.0)
    data={symbol:bars(prices)}
    conversion = 'ETHUSD' if symbol=='BTCETH' else 'BCHUSD'
    if fxprices is not None:
        data[conversion]=bars(fxprices)
    class Feed(FakeKursDaten):
        terminal_pfad='explicit-test-feed'
        def __init__(self):
            super().__init__(data)
            self.terminal_herkunft={}
        def hole_h1(self, s, *args, **kwargs):
            value=super().hole_h1(s,*args,**kwargs)
            if value:
                self.terminal_herkunft[s]=('different-feed' if wrong_feed and s==conversion
                                            else self.terminal_pfad)
            return value
    provider=Feed() if feed else FakeKursDaten(data)
    return er.rekonstruiere(SimpleNamespace(trades=[trade], balances=[], pendings=[]),
        provider, startkapital=10000.0, gmt_offset_h=0), provider


def test_cnh_kehraus_identischer_h1_bar_intraday_und_kein_future(monkeypatch):
    result,_=run(monkeypatch,'USDCNH',[7,6,3,7,0.5])
    # 0.01 lot * 100k * (3-7) CNH / 3 CNH je USD = -1333.333 USD.
    # Zukünftiger Close 0.5 gehört zu Stunde5, nach Trade-Ende Stunde4.
    assert result['verlaesslich'] is True, result
    assert result['equity_dd_usd']==1333.33
    assert result['equity_dd_pct_raw']==pytest.approx(13.3333333333333)
    provenance=result['fx_umrechnungen'][0]
    assert provenance['umrechnungssymbol']=='USDCNH'
    assert provenance['verfuegbare_zeitpunkte']==[EPOCH+i*3600 for i in (1,2,3)]
    assert 'fx_luecke' not in result


def test_cnh_fehlende_h1_bar_bleibt_messluecke(monkeypatch):
    result,_=run(monkeypatch,'USDCNH',[7,6,None,7,0.5])
    assert result['verlaesslich'] is False
    assert result['abdeckung_pct']<95
    assert EPOCH+3*3600 not in result['fx_umrechnungen'][0]['verfuegbare_zeitpunkte']


def test_anderes_cnh_instrument_bekommt_keinen_selbst_kehraus(monkeypatch):
    result,_=run(monkeypatch,'EURCNH',[7,6,3,7])
    assert result['verlaesslich'] is False
    assert result['fx_luecke'] is True
    assert 'fx_umrechnungen' not in result


def test_bch_nutzt_direkten_synchronen_kurs_aus_belegtem_feed(monkeypatch):
    result,provider=run(monkeypatch,'ETHBCH',[7,6,3,7],fxprices=[100,200,500,100])
    # 0.01 lot * 10 * (3-7) BCH * 500 USD/BCH = -200 USD.
    assert result['verlaesslich'] is True, result
    assert result['equity_dd_usd']==200.0
    assert result['fx_umrechnungen'][0]['umrechnungssymbol']=='BCHUSD'
    assert [q[0] for q in provider.abfragen]==['ETHBCH','BCHUSD']


@pytest.mark.parametrize('feed,wrong_feed,fxprices', [
    (False,False,[100,200,500,100]),
    (True,True,[100,200,500,100]),
    (True,False,None),
    (True,False,[100,200,None,100]),
])
def test_bch_unbelegter_feed_oder_fehlender_punkt_bleibt_sperre(
        monkeypatch,feed,wrong_feed,fxprices):
    result,_=run(monkeypatch,'ETHBCH',[7,6,3,7],fxprices=fxprices,
        feed=feed,wrong_feed=wrong_feed)
    assert result['verlaesslich'] is False
    assert result['fx_luecke'] is True


def test_eth_nutzt_direkten_synchronen_kurs_aus_belegtem_feed(monkeypatch):
    result,provider=run(monkeypatch,'BTCETH',[7,6,3,7],fxprices=[1000,2000,5000,1000])
    # 0.01 lot * 1 BTC/lot * (3-7) ETH/BTC * 5000 USD/ETH = -200 USD.
    assert result['verlaesslich'] is True
    assert result['equity_dd_usd']==200.0
    provenance=result['fx_umrechnungen'][0]
    assert provenance['quote']=='ETH'
    assert provenance['umrechnungssymbol']=='ETHUSD'
    assert provenance['formel']=='ETHUSD-H1-Close (USD je ETH)'
    assert [q[0] for q in provider.abfragen]==['BTCETH','ETHUSD']


@pytest.mark.parametrize('feed,wrong_feed,fxprices', [
    (False,False,[1000,2000,5000,1000]),
    (True,True,[1000,2000,5000,1000]),
    (True,False,[1000,2000,None,1000]),
])
def test_eth_fremder_unbelegter_feed_oder_fehlender_punkt_bleibt_sperre(
        monkeypatch,feed,wrong_feed,fxprices):
    result,_=run(monkeypatch,'BTCETH',[7,6,3,7],fxprices=fxprices,
        feed=feed,wrong_feed=wrong_feed)
    assert result['verlaesslich'] is False
    assert result['fx_luecke'] is True
