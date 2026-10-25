"""Zusätzliche isolierte Tabellen-Auditreproduktionen vom 18.10.2026.

Run from project root with `python -m pytest <this file> -q -p no:cacheprovider`.
Uses the project's autouse storage fixture explicitly because this evidence
file deliberately lives outside tests/. No live downloads are performed.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'src'))
from conftest import isolated_app_storage  # noqa: F401,E402

from streamlit.testing.v1 import AppTest
from mqlkiscanner import db, katalog, pipeline


def _two_row_page(monkeypatch):
    rows = [pipeline.ScanResult(id=1, name='Alpha', quelle='audit', herkunft='Workflow'),
            pipeline.ScanResult(id=2, name='Beta', quelle='audit', herkunft='Workflow')]
    monkeypatch.setattr(db, 'list_catalog', lambda: [
        {'signal_id': r.id, 'stats': {}} for r in rows])
    monkeypatch.setattr(db, 'katalog_sync_status', lambda: {'audit': {'anzahl': 2}})
    monkeypatch.setattr(pipeline, 'results_from_db', lambda **kw: rows)
    monkeypatch.setattr(katalog, 'katalog_resultate', lambda **kw: ([], {}))
    at = AppTest.from_file(str(ROOT / 'app_pages' / 'alle_signale.py'), default_timeout=30).run()
    assert not at.exception
    return at


def test_selection_then_filter_keeps_only_valid_row(monkeypatch):
    at = _two_row_page(monkeypatch)
    at.session_state['alle_signale_tabelle'] = {'selection': {'rows': [1]}}
    at.run()
    assert not at.exception
    at.text_input(key='alle_signale_suche').set_value('Alpha').run()
    assert not at.exception, 'Filter must clear a selected index outside the filtered DataFrame'


def test_selection_then_source_change_keeps_only_valid_row(monkeypatch):
    at = _two_row_page(monkeypatch)
    at.session_state['alle_signale_tabelle'] = {'selection': {'rows': [0]}}
    at.run()
    assert not at.exception
    at.text_input(key='alle_signale_suche').set_value('Beta').run()
    assert not at.exception
    # A filter may clear the old selection. It must not silently transfer it
    # to another signal merely because the new row has the same row index.
    selected = at.session_state['alle_signale_tabelle']
    current = selected.selection.rows if hasattr(selected, 'selection') else selected['selection']['rows']
    assert not current, 'The old Alpha selection silently transfers to Beta'


def test_new_bytes_and_sha_at_same_path_refresh_statistics(tmp_path, monkeypatch):
    import hashlib
    from mqlkiscanner import signal_statistik
    from unittest.mock import Mock
    from test_alle_signale_seite import _csv, _probe_mit_trades
    path = Path(_csv(tmp_path / 'replaced.csv'))
    row = _probe_mit_trades(str(path))
    row.trades_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(db, 'list_catalog', lambda: [
        {'signal_id': row.id, 'stats': {'initial_deposit_usd': 10_000}}])
    monkeypatch.setattr(db, 'katalog_sync_status', lambda: {'audit': {'anzahl': 1}})
    monkeypatch.setattr(pipeline, 'results_from_db', lambda **kw: [row])
    monkeypatch.setattr(katalog, 'katalog_resultate', lambda **kw: ([], {}))
    calculate = Mock(wraps=signal_statistik.berechne)
    monkeypatch.setattr(signal_statistik, 'berechne', calculate)
    at = AppTest.from_file(str(ROOT / 'app_pages' / 'alle_signale.py'), default_timeout=30).run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]['Trades'] == 3
    calls_before = calculate.call_count
    # Same file path, valid new delivery with changed registered SHA.
    with path.open('a', encoding='utf-8') as handle:
        handle.write('2026.04.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.04.05 10:10:00;1.1012;0;;130.0\n')
    row.trades_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    at.run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]['Trades'] == 4
    assert calculate.call_count > calls_before
