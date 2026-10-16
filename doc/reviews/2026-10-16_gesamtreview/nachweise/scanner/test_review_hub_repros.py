"""Offline reproductions: passing asserts document observed defective behavior.

These are evidence tests, NOT assertions that the behavior is desirable.
No network, model, broker, terminal or production storage is used.
"""
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

AUDIT = Path(__file__).resolve().parent
sys.path.insert(0, str(AUDIT / 'snapshot' / 'src'))
from mqlkiscanner import config, db, ingest, client_updates, downloader_sync
from mqlkiscanner.agenten import dirigent
from mqlkiscanner.llm.verdict_check import parse_and_validate_portfolio


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    for key, suffix in {'DATA_DIR': 'data', 'CONFIG_DIR': 'config',
                        'DOWNLOADER_DIR': 'data/downloader', 'REPORTS_DIR': 'data/reports'}.items():
        path = tmp_path / suffix
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, key, path)
    monkeypatch.setattr(config, 'SETTINGS_FILE', config.CONFIG_DIR / 'app_settings.json')
    monkeypatch.setattr(db, 'DB_PATH', config.DATA_DIR / 'review.db')
    db.init_db()


def test_mql_downloader_mt4_invents_roboforex_broker():
    data = {'version': 'mql4', 'metrics': {'Balance': 10000, 'Subscribers': 2}}
    result = ingest.metrics_zu_stats(data, quelle_kuerzel='mql5')
    assert result['broker_server'] == 'roboforex'
    print('MT4 Downloader without Broker =>', result['broker_server'])


def test_monthly_exhaustion_still_permits_model_call(monkeypatch):
    lage = {'wochenende': False, 'tagesbudget_tokens': 500000,
            'tokens_heute': 0, 'monatsbudget_tokens': 5000000,
            'tokens_monat': 5000000, 'start_zeit': '06:30'}
    calls = []
    class FakeClient:
        has_key = True
        usage = SimpleNamespace(total_tokens=0)
        def __init__(self, **kwargs):
            self.limit = kwargs['max_total_tokens']
        def chat(self, *args, **kwargs):
            calls.append(self.limit)
            return '{"aktionen": [], "begruendung": "synthetic"}'
    monkeypatch.setattr(dirigent.llm_client, 'GlmClient', FakeClient)
    monkeypatch.setattr(dirigent.rollen_prompts, 'lade_vorlage', lambda _: '{lagestatus_json}')
    monkeypatch.setattr(dirigent.journal, 'schritt_protokollieren', Mock())
    assert dirigent._tagesplan(lage) == ['budget_pause']
    dirigent._llm_entscheidung(lage, {}, 1, lambda _: None)
    assert calls == [500000]
    print('Monthly exhausted: plan=budget_pause, model calls=', len(calls))


def test_update_accepts_done_from_different_job(monkeypatch):
    fake = SimpleNamespace(
        health=lambda: {'status': 'ok'},
        update_starten=lambda **_: {'jobId': 'requested-job', 'bereitsLaufend': False},
        update_status=lambda: {'jobId': 'different-job', 'state': 'done',
                               'done': 1, 'total': 1, 'ergebnis': {'datenstand': 'old-snapshot'}},
    )
    monkeypatch.setattr(client_updates.quellen, 'client_fuer_quelle', lambda *a, **k: fake)
    monkeypatch.setattr(client_updates, '_persistiere', lambda _: None)
    result = client_updates._update_eine_quelle(
        {'id': 1, 'kuerzel': 'synthetic', 'name': 'Synthetic', 'base_url': 'http://unused'},
        settings={}, log=None, on_fortschritt=None, gestopft=lambda: False,
        bereit_warten_s=0, poll_s=0, backoff_s=0, timeout_s=1, login_timeout_s=0)
    assert result['status'] == client_updates.FERTIG
    assert result['job_id'] == 'requested-job'
    assert result['datenstand'] == 'old-snapshot'
    print('Requested requested-job, polled different-job =>', result['status'])


def test_unknown_portfolio_allocation_has_no_warning():
    result = parse_and_validate_portfolio('- Invented Provider — 100 % — Kern', {'Known Provider': '🟢'})
    assert result['allokationen'][0]['name'] == 'Invented Provider'
    assert result['warnungen'] == []
    print('Unknown provider allocated 100%, warnings=', result['warnungen'])


def test_yellow_portfolio_allocation_is_only_warned_and_retained():
    result = parse_and_validate_portfolio('- Yellow Provider — 100 % — Kern', {'Yellow Provider': '🟡'})
    assert result['allokationen'][0]['gewicht_pct'] == 100
    assert result['warnungen']
    print('Yellow allocation retained:', result['allokationen'])


def test_same_size_changed_pdf_is_never_refreshed():
    old = b'%PDF-A1'
    new = b'%PDF-B2'
    class Client:
        def __init__(self):
            self.modified = '2026-01-01'
            self.body = old
            self.downloads = 0
        def reports(self, *args):
            return [{'name': 'report.pdf', 'sizeBytes': len(self.body), 'lastModified': self.modified}]
        def download_report(self, *args):
            self.downloads += 1
            return self.body
    client = Client()
    first = downloader_sync.sync_reports(123, 'pelican', client=client)
    client.modified = '2026-10-16'
    client.body = new
    second = downloader_sync.sync_reports(123, 'pelican', client=client)
    assert len(first) == 1 and second == [] and client.downloads == 1
    assert Path(first[0]).read_bytes() == old
    print('Changed lastModified, same size => old PDF retained')


def test_atomic_cache_temp_collides_for_two_threads(tmp_path, monkeypatch):
    target = tmp_path / 'cache.csv'
    a_written = threading.Event()
    b_written = threading.Event()
    a_replaced = threading.Event()
    original_write = Path.write_bytes
    original_replace = ingest.os.replace
    errors = []
    def controlled_write(path, body):
        if threading.current_thread().name == 'review-A':
            result = original_write(path, body)
            a_written.set()
            assert b_written.wait(5)
            return result
        assert a_written.wait(5)
        result = original_write(path, body)
        b_written.set()
        assert a_replaced.wait(5)
        return result
    def controlled_replace(source, destination):
        try:
            return original_replace(source, destination)
        finally:
            if threading.current_thread().name == 'review-A':
                a_replaced.set()
    def write(body):
        try:
            ingest._atomar_schreiben(target, body)
        except Exception as exc:
            errors.append(type(exc).__name__)
    monkeypatch.setattr(Path, 'write_bytes', controlled_write)
    monkeypatch.setattr(ingest.os, 'replace', controlled_replace)
    threads = [threading.Thread(target=write, args=(b'A',), name='review-A'),
               threading.Thread(target=write, args=(b'B',), name='review-B')]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert errors == ['FileNotFoundError']
    assert target.read_bytes() == b'B'
    print('Two writers: A published B bytes, B raised FileNotFoundError')


def test_cross_source_identity_is_rejected_not_supported():
    db.upsert_signal(123, name='MQL Provider', platform='MT5', quelle='mql5')
    with pytest.raises(ValueError, match='ID-Kollision'):
        db.upsert_signal(123, name='Pelican Provider', platform='pelican', quelle='pelican')
    assert db.get_signal(123)['name'] == 'MQL Provider'
    print('Composite identity missing; collision safely rejected, second provider unavailable')


def test_scan_analysis_costs_are_outside_agent_budget_counters():
    from mqlkiscanner.agenten import journal
    db.upsert_signal(124, name='Synthetic scan provider', quelle='mql5')
    db.store_analysis(124, 'trade_analyse', 'synthetic', 100000, 'synthetic text')
    assert journal.tokens_heute() == 0
    assert journal.tokens_monat() == 0
    print('100000 recorded workflow-analysis tokens => agent day/month counters both 0')
