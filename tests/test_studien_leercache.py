"""A verified empty file must not permanently hide an advertised history."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, ingest, katalog, studien_batch


HEADER = 'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'
TRADE = '2026.01.05 10:00:00;Buy;0.1;EURUSD;1.1;0.1;2026.01.05 11:00:00;1.2;0;0;10\n'


def context(tmp_path, monkeypatch, expected=1, recovered=True):
    empty=tmp_path/'empty.csv'
    empty.write_text(HEADER,encoding='utf-8')
    fresh=tmp_path/'fresh.csv'
    fresh.write_text(HEADER+(TRADE if recovered else ''),encoding='utf-8')
    result=SimpleNamespace(id=123,name='Example',quelle='source',quelle_id=4,
                           quelle_version='vantage',trades_path=str(empty),
                           trades_sha256='empty',kapitalbasis_usd=None,broker_server=None)
    monkeypatch.setattr(katalog,'metrics_stats',lambda _: {'trades':expected})
    monkeypatch.setattr(katalog,'quellen_referenz',lambda _: (4,'vantage'))
    loader=Mock(return_value=(str(fresh),True))
    monkeypatch.setattr(katalog,'lade_signal_daten',loader)
    artifact=Mock(return_value={'sha256':'fresh'})
    monkeypatch.setattr(db,'get_quellen_artefakt',artifact)
    stored=Mock()
    monkeypatch.setattr(db,'store_equity_studie',stored)
    monkeypatch.setattr(studien_batch,'_rekonstruiere_mit_feed_fallback',
                        lambda *a: {'equity_dd_pct':1,'equity_dd_usd':100,'verlaesslich':True})
    return result,loader,artifact,stored


def test_empty_advertised_history_refreshes_once_and_uses_new_sha(tmp_path,monkeypatch):
    result,loader,artifact,stored=context(tmp_path,monkeypatch)
    assert studien_batch._rechne_ein_signal(result,{'skipped_gruende':[]},object(),True)
    loader.assert_called_once_with(result)
    artifact.assert_called_once_with(4,123,'vantage','trades')
    assert result.trades_path.endswith('fresh.csv') and result.trades_sha256=='fresh'
    assert stored.call_args.args[1]=='fresh'


@pytest.mark.parametrize('expected', [0,None,-1,True,float('nan')])
def test_no_positive_trade_evidence_does_not_refresh(tmp_path,monkeypatch,expected):
    result,loader,_,stored=context(tmp_path,monkeypatch,expected)
    assert not studien_batch._rechne_ein_signal(result,{'skipped_gruende':[]},object(),True)
    loader.assert_not_called()
    stored.assert_not_called()


def test_refresh_disabled_preserves_cache(tmp_path,monkeypatch):
    result,loader,_,stored=context(tmp_path,monkeypatch)
    assert not studien_batch._rechne_ein_signal(result,{'skipped_gruende':[]},object(),False)
    loader.assert_not_called()
    stored.assert_not_called()


def test_still_empty_after_refresh_is_not_retried_or_stored(tmp_path,monkeypatch):
    result,loader,_,stored=context(tmp_path,monkeypatch,recovered=False)
    control={'skipped_gruende':[]}
    assert not studien_batch._rechne_ein_signal(result,control,object(),True)
    loader.assert_called_once()
    stored.assert_not_called()
    assert 'keine Trades' in control['skipped_gruende'][0]


def test_failed_refresh_cannot_publish_a_study(tmp_path,monkeypatch):
    result,loader,_,stored=context(tmp_path,monkeypatch)
    loader.side_effect=RuntimeError('Provider session unavailable')
    with pytest.raises(RuntimeError,match='session unavailable'):
        studien_batch._rechne_ein_signal(result,{'skipped_gruende':[]},object(),True)
    stored.assert_not_called()


@pytest.mark.parametrize('counts', [{'Trades':2}, {'Trades':0,'Wins':1}, {'Losses':3}, {'Trades':'2,0'}])
def test_real_metrics_mapping_drives_empty_cache_refresh(tmp_path,monkeypatch,counts):
    result,loader,_,stored=context(tmp_path,monkeypatch,expected=None)
    mapped=ingest.metrics_zu_stats({'version':'vantage','metrics':counts})
    assert mapped.get('trades') is None  # Never a parser position-count hint.
    monkeypatch.setattr(katalog,'metrics_stats',lambda _: dict(mapped))
    assert studien_batch._rechne_ein_signal(result,{'skipped_gruende':[]},object(),True)
    loader.assert_called_once_with(result)
    stored.assert_called_once()


@pytest.mark.parametrize('counts', [{'Trades':True}, {'Wins':float('nan')},
                                   {'Losses':float('inf')}, {'Trades':0,'Wins':0,'Losses':0},
                                   {'Trades':0.5}, {'Wins':-1}])
def test_invalid_or_zero_source_counts_do_not_force_refresh(tmp_path,monkeypatch,counts):
    result,loader,_,stored=context(tmp_path,monkeypatch,expected=None)
    mapped=ingest.metrics_zu_stats({'version':'vantage','metrics':counts})
    monkeypatch.setattr(katalog,'metrics_stats',lambda _: dict(mapped))
    assert not studien_batch._rechne_ein_signal(result,{'skipped_gruende':[]},object(),True)
    loader.assert_not_called()
    stored.assert_not_called()
