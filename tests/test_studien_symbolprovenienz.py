"""Persist successful broker-name evidence, never a later provider's RAM state."""
import datetime as dt
from types import SimpleNamespace

import pytest

from mqlkiscanner import db, equity_studie, kursdaten, studien_batch
from mqlkiscanner.forensics import equity_rekonstruktion


class Feeds:
    def __init__(self, mappings):
        self.mappings = mappings
        self.terminal_idx = 0
        self.terminal_herkunft = {}
        self.suffix_annahmen = {}
        self.symbol_herkunft = {}

    @property
    def terminal_pfad(self): return 'feed-' + str(self.terminal_idx)
    def hat_weiteren_terminal(self): return self.terminal_idx + 1 < len(self.mappings)
    def wechsle_terminal(self):
        self.terminal_idx += 1
        return True, 'synthetic'
    def zurueck_zum_ersten_terminal(self):
        self.terminal_idx = 0
        self.terminal_herkunft.clear()
        self.suffix_annahmen.clear()
        self.symbol_herkunft.clear()
        return True, 'synthetic cleanup'
    def hole_h1(self, symbol, von, bis, *args, **kwargs):
        target = self.mappings[self.terminal_idx].get(symbol)
        if not target: return None
        self.terminal_herkunft[symbol] = self.terminal_pfad
        self.suffix_annahmen[symbol] = target
        self.symbol_herkunft[symbol] = {'terminal': self.terminal_pfad, 'broker_symbol': target}
        value = 2000. if symbol == 'XAUUSD' else 1.1
        return [{'time': t, 'open': value, 'close': value, 'high': value, 'low': value}
                for t in range((int(von)//3600)*3600, int(bis)+3601, 3600)]


def parsed(symbols=('XAUUSD',)):
    start = dt.datetime(2026, 1, 5, 10)
    trades = [SimpleNamespace(symbol=s, open_time=start, close_time=start+dt.timedelta(hours=3),
        direction='buy', volume=.01, entry_price=2000. if s == 'XAUUSD' else 1.1,
        exit_price=2000. if s == 'XAUUSD' else 1.1, net=0.) for s in symbols]
    return SimpleNamespace(trades=trades, balances=[], pendings=[])


def report(valid=True, coverage=100):
    return dict(status='ok', equity_dd_pct_raw=5., equity_dd_usd=50.,
                abdeckung_pct=coverage, verlaesslich=valid,
                symbole_mit_kursen=['XAUUSD'])


def test_exact_configured_suffix_also_has_successful_broker_name_evidence(monkeypatch):
    provider = kursdaten.KursDaten({'markt_terminal_pfad': 'synthetic-terminal', 'markt_symbol_suffix': '+'})
    provider._aktiv = True
    provider._mt5 = SimpleNamespace(symbol_select=lambda *a: True)
    monkeypatch.setattr(provider, '_hole_terminal_h1', lambda symbol, start, end:
                        [{'time': start, 'open': 1., 'close': 1., 'high': 1., 'low': 1.}])
    provider.hole_h1('XAUUSD', 1_700_002_800, 1_700_002_800)
    assert provider.suffix_annahmen == {}  # Exact configured target was not an assumption.
    assert provider.symbol_herkunft['XAUUSD']['broker_symbol'] == 'XAUUSD+'


def test_empty_read_removes_only_its_own_successful_metadata(monkeypatch):
    provider = kursdaten.KursDaten({'markt_terminal_pfad': 'synthetic-terminal'})
    provider._aktiv = True
    provider._mt5 = SimpleNamespace(symbol_select=lambda *a: True)
    monkeypatch.setattr(provider, '_hole_terminal_h1', lambda symbol, start, end:
                        [{'time': start, 'open': 1., 'close': 1., 'high': 1., 'low': 1.}])
    for symbol in ('XAUUSD', 'EURUSD'): provider.hole_h1(symbol, 1_700_002_800, 1_700_002_800)
    monkeypatch.setattr(provider, '_hole_terminal_h1', lambda *a: [])
    assert provider.hole_h1('EURUSD', 1_700_010_000, 1_700_010_000) is None
    assert set(provider.symbol_herkunft) == {'XAUUSD'}


@pytest.mark.parametrize('selected', [0, 1])
def test_selected_report_and_each_attempt_keep_their_own_name_after_reset(monkeypatch, selected):
    provider = Feeds([{'XAUUSD': 'GOLD.primary'}, {'XAUUSD': 'XAUUSD+'}])
    def reconstruct(data, source, *args, **kwargs):
        source.hole_h1('XAUUSD', 1_700_002_800, 1_700_002_800)
        return report(valid=selected == 1 and provider.terminal_idx == 1,
                      coverage=(99 if provider.terminal_idx == selected else 80))
    monkeypatch.setattr(equity_rekonstruktion, 'rekonstruiere', reconstruct)
    result = studien_batch._rekonstruiere_mit_feed_fallback(parsed(), provider, 1000., None)
    target = provider.mappings[selected]['XAUUSD']
    assert provider.symbol_herkunft == {}  # Cleanup already destroyed mutable provider state.
    assert result['symbol_substitutionen'] == {'XAUUSD': target}
    assert result['symbol_herkunft']['XAUUSD'] == {'terminal': 'feed-'+str(selected), 'broker_symbol': target}
    attempts = result['kursdaten_versuche']
    assert attempts[0]['symbol_substitutionen'] == {'XAUUSD': 'GOLD.primary'}
    assert attempts[1]['symbol_substitutionen'] == {'XAUUSD': 'XAUUSD+'}
    attempts[selected]['symbol_herkunft']['XAUUSD']['broker_symbol'] = 'changed later'
    assert result['symbol_herkunft']['XAUUSD']['broker_symbol'] == target


def test_symbol_fallback_is_captured_before_internal_reset_and_excludes_stale_symbols(monkeypatch):
    provider = Feeds([{'XAUUSD': 'GOLD.primary'}, {'EURUSD': 'EURUSD+'}])
    provider.symbol_herkunft['GBPUSD'] = {'terminal': 'old', 'broker_symbol': 'OLD'}
    def reconstruct(data, source, *args, **kwargs):
        source.hole_h1('XAUUSD', 1_700_002_800, 1_700_002_800)
        provider.wechsle_terminal()
        source.hole_h1('EURUSD', 1_700_002_800, 1_700_002_800)
        provider.zurueck_zum_ersten_terminal()
        return dict(report(), symbole_mit_kursen=['XAUUSD', 'EURUSD', 'GBPUSD'])
    monkeypatch.setattr(equity_rekonstruktion, 'rekonstruiere', reconstruct)
    result = studien_batch._rekonstruiere_mit_feed_fallback(parsed(('XAUUSD', 'EURUSD', 'GBPUSD')), provider, 1000., None)
    assert result['symbol_substitutionen'] == {'XAUUSD': 'GOLD.primary', 'EURUSD': 'EURUSD+'}
    assert result['symbol_feeds'] == {'XAUUSD': 'feed-0', 'EURUSD': 'feed-1'}
    assert 'GBPUSD' not in result['symbol_herkunft']


def test_direct_study_persists_mixed_feed_names_even_after_cleanup():
    provider = Feeds([{'XAUUSD': 'GOLD.primary'}, {'EURUSD': 'EURUSD+'}])
    result = equity_studie.studie(parsed(('XAUUSD', 'EURUSD')), provider, 1000., gmt_offset_h=0)
    assert result['status'] == 'ok'
    assert result['symbol_substitutionen'] == {'XAUUSD': 'GOLD.primary', 'EURUSD': 'EURUSD+'}
    assert result['symbol_feeds'] == {'XAUUSD': 'feed-0', 'EURUSD': 'feed-1'}
    db.store_equity_studie(7, 'synthetic', result, quelle='native')
    assert db.get_equity_studie(7, quelle='native')['report']['symbol_herkunft'] == result['symbol_herkunft']


@pytest.mark.parametrize('known_alias', [None, 'GOLD.legacy'])
def test_legacy_provider_without_name_evidence_never_invents_an_exact_match(monkeypatch, known_alias):
    class Legacy:
        terminal_pfad = 'legacy-feed'
        terminal_herkunft = {}
        suffix_annahmen = {'XAUUSD': known_alias} if known_alias else {}
        def hole_h1(self, *args, **kwargs): return [{'time': 1, 'close': 1.}]
    def reconstruct(data, source, *args, **kwargs):
        source.hole_h1('XAUUSD', 0, 1)
        return report()
    monkeypatch.setattr(equity_rekonstruktion, 'rekonstruiere', reconstruct)
    result = studien_batch._rekonstruiere_mit_feed_fallback(parsed(), Legacy(), 1000., None)
    assert result['symbol_substitutionen'] == ({'XAUUSD': known_alias} if known_alias else {})
    expected = {'terminal': 'legacy-feed'}
    if known_alias: expected['broker_symbol'] = known_alias
    assert result['symbol_herkunft'] == {'XAUUSD': expected}


def test_failed_later_attempt_keeps_its_own_read_evidence_without_changing_selection(monkeypatch):
    provider = Feeds([{'XAUUSD': 'GOLD.primary'}, {'XAUUSD': 'XAUUSD+'}])
    def reconstruct(data, source, *args, **kwargs):
        source.hole_h1('XAUUSD', 1_700_002_800, 1_700_002_800)
        if provider.terminal_idx == 1: raise ValueError('synthetic later calculation failure')
        return report(valid=False)
    monkeypatch.setattr(equity_rekonstruktion, 'rekonstruiere', reconstruct)
    result = studien_batch._rekonstruiere_mit_feed_fallback(parsed(), provider, 1000., None)
    assert result['symbol_substitutionen'] == {'XAUUSD': 'GOLD.primary'}
    assert result['kursdaten_versuche'][1]['symbol_substitutionen'] == {'XAUUSD': 'XAUUSD+'}
