"""Report selection and freshness must distinguish new writes from cache reuse."""
from unittest.mock import Mock
# The pipeline-only fixture disables sleep globally; AppTest needs the real
# function while waiting for its script thread to deliver widget messages.
from time import sleep as real_sleep

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, warte_auf_lauf
from mqlkiscanner import db, pipeline, secrets_store
from mqlkiscanner.llm import client
from test_review15_reports import live_reports as live_reports


def start_page():
    return AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30).run()


def finish(at, button):
    at.button(key=button).click().run()
    warte_auf_lauf(at)
    assert not at.exception


@pytest.mark.parametrize('old_report,rebuild', [(True, False), (True, True), (False, False)])
def test_only_new_downloads_still_consider_all_reports(live_reports, monkeypatch, old_report, rebuild):
    pipe, path, scan = live_reports
    monkeypatch.setattr(pipeline.time, 'sleep', real_sleep)
    old = scan()
    if old_report:
        pipe.run_llm([old], lambda _: None)
    monkeypatch.setattr(secrets_store, 'get_secret', lambda key: 'dummy')
    monkeypatch.setattr(client.GlmClient, 'chat', lambda *a, **k: 'Fresh report')
    from mqlkiscanner.mql5 import browser_session
    monkeypatch.setattr(browser_session, 'ensure_mql5_cookies', lambda *a, **k: True)
    candidates = [{'id': i, 'name': str(i), 'platform': 'MT4'} for i in (123, 456)]
    monkeypatch.setattr(pipeline.ScanPipeline, 'crawl', lambda *a, **k: candidates)
    monkeypatch.setattr(pipeline.ScanPipeline, 'build_candidates', lambda *a, **k: candidates)
    exported = []
    def export(session, sid, **kwargs):
        exported.append(sid)
        return str(path), False
    monkeypatch.setattr(pipeline.exporter, 'export_positions', export)
    original = pipeline.ScanPipeline.run_llm
    sent = []
    def run(self, results, *args, **kwargs):
        sent.extend(r.id for r in results)
        return original(self, results, *args, **kwargs)
    monkeypatch.setattr(pipeline.ScanPipeline, 'run_llm', run)
    monkeypatch.setattr(pipeline.ScanPipeline, 'run_portfolio', lambda *a, **k: {'text': 'Portfolio'})
    at = start_page()
    at.toggle(key='scan_nur_neue').set_value(True).run()
    at.toggle(key='scan_llm_neu').set_value(rebuild).run()
    finish(at, 'scan_start')
    assert exported == [456]
    assert set(sent) == ({456} if old_report and not rebuild else {123, 456})
    assert all(r.gesamtbericht for r in at.session_state['scan_results'])
    assert set(at.session_state['refreshed_signal_ids']) == set(sent)
    assert at.session_state['scan_new_ids'] == [456]


def test_cached_only_run_has_explicit_empty_freshness(live_reports, monkeypatch):
    pipe, _, scan = live_reports
    monkeypatch.setattr(pipeline.time, 'sleep', real_sleep)
    pipe.run_llm([scan()], lambda _: None)
    monkeypatch.setattr(secrets_store, 'get_secret', lambda key: 'dummy')
    candidates = [{'id': 123, 'name': 'Cached', 'platform': 'MT4'}]
    monkeypatch.setattr(pipeline.ScanPipeline, 'crawl', lambda *a, **k: candidates)
    monkeypatch.setattr(pipeline.ScanPipeline, 'build_candidates', lambda *a, **k: candidates)
    monkeypatch.setattr(pipeline.ScanPipeline, 'analyze_candidate', Mock(side_effect=AssertionError('cached')))
    monkeypatch.setattr(pipeline.ScanPipeline, 'run_llm', Mock(side_effect=AssertionError('matching report')))
    monkeypatch.setattr(pipeline.ScanPipeline, 'run_portfolio', lambda *a, **k: {'text': 'Portfolio'})
    at = start_page()
    at.session_state['refreshed_signal_ids'] = [123]  # previous run must not leak
    at.toggle(key='scan_nur_neue').set_value(True).run()
    finish(at, 'scan_start')
    assert at.session_state['refreshed_signal_ids'] == []
    at.switch_page('app_pages/ergebnisse.py').run()
    assert not at.exception
    assert list(at.dataframe[0].value['Stand']) == ['']
    assert at.toggle(key='results_only_fresh').disabled


@pytest.mark.parametrize('storage', ['ok', 'partial', 'failed'])
def test_llm_only_freshness_requires_at_least_one_saved_report(live_reports, monkeypatch, storage):
    pipe, _, scan = live_reports
    monkeypatch.setattr(pipeline.time, 'sleep', real_sleep)
    scan()
    monkeypatch.setattr(secrets_store, 'get_secret', lambda key: 'dummy')
    monkeypatch.setattr(client.GlmClient, 'chat', lambda *a, **k: 'Fresh report')
    original = db.store_analysis
    def store(signal_id, kind, *args, **kwargs):
        if storage == 'failed' or (storage == 'partial' and kind == 'trade_analyse'):
            raise RuntimeError('simulated storage failure')
        return original(signal_id, kind, *args, **kwargs)
    monkeypatch.setattr(db, 'store_analysis', store)
    at = start_page()
    at.session_state['scan_results'] = pipeline.results_from_db(pipe.settings)
    at.session_state['refreshed_signal_ids'] = [999]
    at.run()
    finish(at, 'step_btn_llm')
    assert at.session_state['refreshed_signal_ids'] == ([] if storage == 'failed' else [123])
    assert at.session_state['scan_results'][0].trade_analyse == 'Fresh report'


@pytest.mark.parametrize('freshness,expected', [(None, 'NEU'), ([], '')])
def test_legacy_unknown_freshness_differs_from_explicit_empty(freshness, expected):
    db.init_db()
    db.upsert_signal(123, name='Example')
    at = start_page()
    at.session_state['scan_results'] = [pipeline.ScanResult(id=123)]
    at.session_state['refreshed_signal_ids'] = freshness
    at.switch_page('app_pages/ergebnisse.py').run()
    assert not at.exception
    assert list(at.dataframe[0].value['Stand']) == [expected]
