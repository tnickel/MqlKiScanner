import json
from pathlib import Path
import pytest
from mqlkiscanner import config,symbols
from mqlkiscanner.forensics import exposure

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('name,factor,quote',[
 ('UK100',1,'GBP'),('US2000',1,'USD'),('EU50',1,'EUR'),('LTCUSD',100,'USD'),('BNBUSD',10,'USD'),
 ('LYFT',1,'USD'),('NFLX',1,'USD'),('PINS',1,'USD'),('SPCE',1,'USD'),('TTD',1,'USD'),('ORCL',1,'USD')])
def test_exact_vantage_instruments_match_live_broker_evidence(monkeypatch,name,factor,quote):
    monkeypatch.setattr(config,'CONTRACT_SPECS_FILE',ROOT/'data/contract_specs.json')
    live=json.loads((ROOT/'tests/fixtures/vantage_symbol_specs_2026-10-10.json').read_text(encoding='utf8'))['Vantage'][name]
    for instrument in (name,name+'+'):
        spec=symbols.spec_for(instrument,broker='Vantage International Group Limited')
        assert spec['contract_size']==factor==live['contract_size']
        assert spec['quote_currency']==quote==live['gewinnwaehrung']
        assert spec['cross_broker'] is False
        assert spec['brokers']==['vantage']
        assert spec['aliases']==[name]
        resolved=exposure._resolve_symbol(instrument,'Vantage')
        assert resolved['factor']==factor and resolved['quote']==quote
        for other in (None,'Zulu','Tickmill','ActivTrades','RoboForex'):
            foreign=symbols.spec_for(instrument,broker=other)
            assert foreign is None or 'vantage' not in foreign.get('brokers', [])
    if name not in ('UK100','US2000','EU50'):
        assert spec['stress_move_pct']==10
        assert 'keine Brokerspec' in spec['note']


def test_cash_index_spec_is_separate_from_future(monkeypatch):
    monkeypatch.setattr(config,'CONTRACT_SPECS_FILE',ROOT/'data/contract_specs.json')
    cash=symbols.spec_for('UK100',broker='Vantage')
    future=symbols.spec_for('UK100FT',broker='Vantage')
    assert cash is not future
    assert cash['aliases']==['UK100']
    assert 'UK100FT' not in cash['aliases']
    assert 'Vantage.UK100:' in cash['source']


def test_vantage_crypto_sizes_do_not_unlock_unknown_zulu_contract(monkeypatch):
    monkeypatch.setattr(config,'CONTRACT_SPECS_FILE',ROOT/'data/contract_specs.json')
    assert exposure._resolve_symbol('LTCUSD','Zulu') is None
    assert exposure.shock_usd(1,1,'LTCUSD',broker='Vantage')==100
    assert exposure.shock_usd(1,1,'BNBUSD',broker='Vantage')==10


def test_existing_roboforex_nflx_size_is_preserved(monkeypatch):
    monkeypatch.setattr(config,'CONTRACT_SPECS_FILE',ROOT/'data/contract_specs.json')
    assert exposure._resolve_symbol('NFLX','RoboForex')['factor']==100
    assert exposure._resolve_symbol('NFLX','Vantage')['factor']==1
