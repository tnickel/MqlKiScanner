"""Source collisions must remain visible without borrowing another source's data."""
import hashlib
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import db, equity_studie_ui, katalog, pipeline
from mqlkiscanner.signal_identity import AmbiguousSignalIdentity


CSV = (
    'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'
    '2026.01.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.05 10:10:00;1.1010;0;0;100\n'
    '2026.02.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.02.05 10:10:00;1.0990;0;0;-60\n'
    '2026.04.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.04.05 10:10:00;1.1012;0;0;120\n'
).encode()


def seed(tmp_path, workflow=False):
    db.init_db()
    for index, source in enumerate(('alpha', 'beta'), 1):
        qid = db.add_quelle(source, source, f'http://synthetic-{source}:8199')
        db.katalog_upsert_many(source, [dict(signal_id=42, name=source, version='mql5',
            platform='mt5', abonnenten=20 - index, wochen=50)])
        metrics = json.dumps({'signalId': 42, 'version': 'mql5', 'metrics': {
            'Currency': 'USD', 'InitialDeposit': index * 1000,
            'EquityDrawdown': index * 10, 'Broker': source}}).encode()
        for kind, payload in (('trades', CSV), ('metrics', metrics)):
            path = tmp_path / f'{source}_{kind}.csv'
            path.write_bytes(payload)
            db.store_quellen_artefakt(qid, 42, 'mql5', kind,
                                      hashlib.sha256(payload).hexdigest(), str(path))
        db.katalog_sync_vermerken(source, 1)
    if workflow:
        db.store_scan_result(42, dict(name='alpha', quelle='alpha', platform='MT5',
            stats={'account_currency': 'USD', 'initial_deposit_usd': 1000}),
            str(tmp_path / 'alpha_trades.csv'))


def test_same_id_keeps_both_sources_and_their_own_metrics(tmp_path):
    seed(tmp_path)
    rows, stats = katalog.katalog_resultate(gescannt=set(), studien={})
    assert {katalog.signal_identitaet(row) for row in rows} == {('alpha', 42), ('beta', 42)}
    assert stats[('alpha', 42)]['initial_deposit_usd'] == 1000
    assert stats[('beta', 42)]['initial_deposit_usd'] == 2000
    assert {row.quelle: row.dd_equity_pct for row in rows} == {'alpha': 10, 'beta': 20}
    assert {row.quelle: row.broker_server for row in rows} == {'alpha': 'alpha', 'beta': 'beta'}


def test_workflow_dedup_only_removes_same_source_and_id(tmp_path):
    seed(tmp_path, workflow=True)
    rows, stats = katalog.katalog_resultate(studien={})
    assert [(row.quelle, row.id) for row in rows] == [('beta', 42)]
    assert rows[0].trades_path == str(tmp_path / 'beta_trades.csv')
    assert set(stats) == {('beta', 42)}


def test_identical_trade_bytes_do_not_authorize_source_agnostic_study(tmp_path):
    seed(tmp_path)
    unscoped = {42: dict(trades_sha=hashlib.sha256(CSV).hexdigest(), dd_usd=999,
        report={'verlaesslich': True, 'equity_dd_pct_raw': 50})}
    with pytest.raises(AmbiguousSignalIdentity):
        katalog.katalog_resultate(gescannt=set(), studien=unscoped)
    rows, _ = katalog.katalog_resultate(gescannt=set(), studien={})
    scoped = {(row.quelle, row.id): dict(trades_sha=hashlib.sha256(CSV).hexdigest(),
        dd_usd=value * 100, report={'verlaesslich': True, 'equity_dd_pct': value})
        for row, value in zip(rows, (10, 20))}
    rows, _ = katalog.katalog_resultate(gescannt=set(), studien=scoped)
    assert {row.quelle: row.true_max_drawdown_pct for row in rows} == {'alpha': 10, 'beta': 20}


@pytest.mark.parametrize('workflow', [False, True])
def test_real_catalogue_to_page_keeps_source_statistics_separate(tmp_path, workflow):
    seed(tmp_path, workflow)
    at = AppTest.from_file(str(ROOT / 'app_pages/alle_signale.py'), default_timeout=45).run()
    assert not at.exception, at.exception
    frame = at.dataframe[0].value.set_index('Quelle')
    assert set(frame.index) == {'alpha', 'beta'}
    assert list(frame['ID']) == [42, 42]
    assert frame.loc['alpha', 'Geom. %/M'] != frame.loc['beta', 'Geom. %/M']
    if workflow:
        assert pd.isna(frame.loc['alpha', 'Plattform-DD %'])
    else:
        assert frame.loc['alpha', 'Plattform-DD %'] == 10
    assert frame.loc['beta', 'Plattform-DD %'] == 20
    assert all(pd.isna(value) for value in frame['True-DD %'])


def test_qualified_studies_coexist_but_wrong_owner_stops_before_terminal(tmp_path, monkeypatch):
    seed(tmp_path)
    rows, _ = katalog.katalog_resultate(gescannt=set(), studien={})
    def forbidden(*args, **kwargs):
        raise AssertionError('No terminal may be touched for ambiguous study identity')
    monkeypatch.setattr(equity_studie_ui.kursdaten, 'KursDaten', forbidden)
    for row in rows:
        katalog.require_eindeutige_studien_identitaet(row)
    with pytest.raises(AmbiguousSignalIdentity):
        db.resolve_identity(42)
    rows[0].signal_ref = rows[1].signal_ref
    with pytest.raises(ValueError):
        equity_studie_ui.berechne(rows[0], lambda *args: None)


@pytest.mark.parametrize('field,value', [('quelle', 'beta'), ('quelle_version', 'mql4'),
                                        ('broker_server', 'OtherBroker')])
def test_study_session_cache_includes_source_and_contract_scope(field, value):
    first = pipeline.ScanResult(id=42, quelle='alpha', quelle_version='mql5',
                                platform='MT5', trades_sha256='a' * 64)
    original = equity_studie_ui._cache_key(first)
    setattr(first, field, value)
    assert equity_studie_ui._cache_key(first) != original
