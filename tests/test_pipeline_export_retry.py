"""Retry eines unvollstaendigen Downloads bleibt ein echter zweiter Abruf."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import sqlite3

from mqlkiscanner import db, pipeline
from mqlkiscanner.mql5 import exporter


def test_retry_bad_csv_laesst_zweiten_download_zu(tmp_path, monkeypatch):
    header = 'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'
    bad = header + '2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0\n'
    good = header + '2025.12.31 00:00:00;Balance;;;;;;;;;1000\n' + '2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0;10\n'
    monkeypatch.setattr(exporter, 'TRADES_DIR', tmp_path / 'exports')
    monkeypatch.setattr(pipeline.signal_stats, 'fetch_signal_stats',
                        lambda *_: {'account_currency':'USD','dd_equity_pct':5,'monthly_growth_pct':10,
                                    'quelle_trades_gekappt':True,
                                    'quelle_trades_total_available':42000,
                                    'quelle_trades_stored':2000,
                                    'quelle_trades_completeness_note':'Nur gelieferter Teil'})
    monkeypatch.setattr(pipeline.time, 'sleep', lambda _:None)
    remote = Mock(side_effect=[bad, good])
    messages=[]
    assert db.DB_PATH.is_relative_to(tmp_path)
    result = pipeline.ScanPipeline(settings={'equity_rekonstruktion':False}).analyze_candidate(
        SimpleNamespace(export_positions_csv=remote), {'id':123}, messages.append)
    assert remote.call_count == 2, messages
    assert not result.fehler and result.forensik_vorhanden, messages
    stored = json.loads(db.get_signal(123)['stats_json'])
    assert stored['quelle_trades_gekappt'] is True
    assert stored['quelle_trades_total_available'] == 42000
    assert stored['quelle_trades_stored'] == 2000
    assert stored['quelle_trades_completeness_note'] == 'Nur gelieferter Teil'


def test_schemafehler_bleibt_diagnostizierter_einzelfehler(tmp_path, monkeypatch):
    assert db.DB_PATH.is_relative_to(tmp_path)
    def nicht_verfuegbar():
        raise sqlite3.OperationalError('isolated database unavailable')
    monkeypatch.setattr(db,'init_db',nicht_verfuegbar)
    monkeypatch.setattr(pipeline.time,'sleep',lambda _:None)
    remote=Mock()
    result=pipeline.ScanPipeline(settings={'equity_rekonstruktion':False}).analyze_candidate(
        SimpleNamespace(export_positions_csv=remote),{'id':321},lambda _:None)
    assert 'isolated database unavailable' in result.fehler
    assert not result.forensik_vorhanden
    remote.assert_not_called()
