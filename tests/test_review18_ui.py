"""Selections must identify a CSV result, not just its possibly repeated signal ID."""
from types import SimpleNamespace
from time import sleep as real_sleep

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import app_ui, config, pipeline
from test_review15_reports import live_reports as live_reports


def test_results_table_includes_report_creation_date():
    result = pipeline.ScanResult(
        id=123,
        name='Dated report',
        gesamtbericht='Report',
        gesamtbericht_at='2026-09-18 17:42:00',
    )
    frame = app_ui.results_to_dataframe([result])
    assert frame.loc[0, 'Bericht vom'] == pd.Timestamp('2026-09-18 17:42:00')


@pytest.fixture
def distinct_snapshots(live_reports, monkeypatch, tmp_path):
    _, source, _ = live_reports
    monkeypatch.setattr(pipeline.time, 'sleep', real_sleep)
    monkeypatch.setattr(config, 'KNOWN_SIGNALS_FILE', tmp_path / 'no-known-signals.json')
    good, bad = tmp_path / 'first_900001.csv', tmp_path / 'second_900001.csv'
    good.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
    bad.write_text(source.read_text(encoding='utf-8').replace(';1990;2010;', ';;2010;'), encoding='utf-8')
    results = pipeline.ScanPipeline.analyze_local_files([str(good), str(bad)])
    assert results[0].id == results[1].id
    assert results[0].stop_evidence == 'direct' and results[1].stop_evidence == 'none'
    return results


def choose_second_row(monkeypatch):
    original = app_ui.st.dataframe
    def dataframe(*args, **kwargs):
        original(*args, **kwargs)
        return SimpleNamespace(selection=SimpleNamespace(rows=[1]))
    monkeypatch.setattr(app_ui.st, 'dataframe', dataframe)


@pytest.mark.parametrize('page', ['scan', 'ergebnisse'])
def test_second_snapshot_opens_its_own_detail(distinct_snapshots, monkeypatch, page):
    choose_second_row(monkeypatch)
    at = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30)
    at.session_state['scan_results'] = distinct_snapshots
    at.run()
    if page == 'ergebnisse':
        at.switch_page('app_pages/ergebnisse.py').run()
        at.selectbox(key='results_run').set_value('Aktuelle Sitzung').run()
    assert not at.exception
    assert any(distinct_snapshots[1].name in item.value for item in at.subheader)
    assert not any(distinct_snapshots[0].name in item.value for item in at.subheader)


@pytest.mark.parametrize('signal_id', [900001, 0])
def test_report_button_keeps_snapshot_identity_after_filter(distinct_snapshots, monkeypatch, signal_id):
    first, second = distinct_snapshots
    first.id = second.id = signal_id
    first.gesamtbericht, second.gesamtbericht = 'FIRST REPORT', 'SECOND REPORT'
    click_pending = True
    def click_second(*args, **kwargs):
        nonlocal click_pending
        if click_pending:
            column = kwargs['column_config']['Bericht']
            app_ui.st.session_state[column.key] = SimpleNamespace(row=1)
            column.on_click()
            click_pending = False
        return SimpleNamespace(selection=SimpleNamespace(rows=[]))
    monkeypatch.setattr(app_ui.st, 'dataframe', click_second)
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.app_ui import render_results_table, render_report_panel\n"
        "render_results_table(st.session_state.rows)\n"
        "render_report_panel(st.session_state.rows)", default_timeout=30)
    at.session_state['rows'] = distinct_snapshots
    at.run()
    assert not at.exception
    assert any('SECOND REPORT' in item.value for item in at.markdown)
    assert not any('FIRST REPORT' in item.value for item in at.markdown)
    # Hiding the chosen file must not silently substitute another file of the same ID.
    at.session_state['rows'] = [first]
    at.run()
    assert not at.exception
    assert 'report_signal_id' not in at.session_state
    assert not any('FIRST REPORT' in item.value for item in at.markdown)


def test_ambiguous_legacy_id_selection_is_cleared(distinct_snapshots):
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.app_ui import render_report_panel\n"
        "render_report_panel(st.session_state.rows)", default_timeout=30)
    at.session_state['rows'] = distinct_snapshots
    at.session_state['report_signal_id'] = distinct_snapshots[0].id
    at.run()
    assert not at.exception
    assert 'report_signal_id' not in at.session_state
