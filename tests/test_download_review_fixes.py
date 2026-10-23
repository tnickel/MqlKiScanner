"""Regressionen der Downloadprüfung: Vollkatalog, Hinweise und freie DD-Grenze."""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import alle_signale_ui, config, db, downloader_client, ingest, katalog, pipeline


def item(signal_id):
    return {"signalId": signal_id, "version": "zulu"}


class Pages:
    def __init__(self, pages):
        self.pages = iter(pages)

    def katalog(self, *, limit, offset, min_subscribers=1):
        return next(self.pages)


@pytest.mark.parametrize("pages", [
    [{"items": [item(1)], "total": 3}, {"items": [], "total": 3}],
    [{"items": [item(1)], "total": 3}, {"items": [item(2)], "total": 2}],
    [{"items": [item(1)], "total": 2}, {"items": [item(1)], "total": 2}],
    [{"items": [item(1)], "total": 1, "offset": 1}],
    [{"items": [item(1)], "total": 0}],
    [{"items": []}],
    [{"items": [], "total": True}],
    [{"items": [], "total": -1}],
    [{"items": {}, "total": 0}],
])
def test_invalid_catalog_never_replaces_previous_stock(pages, monkeypatch):
    db.init_db()
    db.katalog_upsert_many("broken", [{"signal_id": n} for n in (1, 2, 3)])
    sources = [{"id": 1, "kuerzel": "broken"}, {"id": 2, "kuerzel": "healthy"}]
    monkeypatch.setattr(katalog.quellen, "_ensure", lambda: None)
    monkeypatch.setattr(db, "list_quellen", lambda **kw: sources)
    clients = {"broken": Pages(pages), "healthy": Pages([{"items": [item(9)], "total": 1}])}
    monkeypatch.setattr(ingest.quellen, "client_fuer_quelle", lambda source: clients[source['kuerzel']])
    summary = katalog.sync()
    assert summary['quellen']['broken']['fehler']
    assert summary['quellen']['broken']['geloescht'] == 0
    assert {row['signal_id'] for row in db.katalog_list() if row['quelle'] == 'broken'} == {1, 2, 3}
    assert summary['quellen']['healthy']['anzahl'] == 1
    assert db.katalog_sync_status()['broken']['fehler']


def test_page_limit_is_a_failure_not_a_complete_catalog():
    with pytest.raises(downloader_client.DownloaderError, match="Seitenlimit"):
        ingest.hole_katalog({}, client=Pages([{"items": [item(1)], "total": 2}]), max_seiten=1)


def test_complete_raw_catalog_allows_invalid_id_normalization():
    raw = ingest.hole_katalog({}, client=Pages([
        {"items": [item(1)], "total": 2, "offset": 0},
        {"items": [item("test_1")], "total": 2, "offset": 1}]))
    assert len(raw) == 2
    assert [row['signal_id'] for row in katalog._normalisiere(raw)] == [1]


def test_proven_empty_catalog_can_remove_old_catalog_entries(monkeypatch):
    db.katalog_upsert_many("empty", [{"signal_id": 1}])
    monkeypatch.setattr(katalog.quellen, "_ensure", lambda: None)
    monkeypatch.setattr(db, "list_quellen", lambda **kw: [{"id": 1, "kuerzel": "empty"}])
    monkeypatch.setattr(ingest.quellen, "client_fuer_quelle",
                        lambda source: Pages([{"items": [], "total": 0}]))
    result = katalog.sync()
    assert result['quellen']['empty']['fehler'] is None
    assert result['quellen']['empty']['geloescht'] == 1


@pytest.mark.parametrize("field", ['TradesCompletenessNote', 'CompletenessNote'])
def test_source_history_note_reaches_visible_table_status(field):
    note = 'Cache kann gekappt oder älter sein; gleiche Anzahl ist kein Vollständigkeitsbeweis.'
    stats = ingest.metrics_zu_stats({'version': 'zulu', 'metrics': {
        field: note, 'TradesTruncated': True, 'TradesStored': 1164, 'TradesTotalAvailable': 8992}})
    result = pipeline.ScanResult(id=430306, name='History', platform='zulu', quelle='zulu', account_currency='USD')
    row = alle_signale_ui.tabellen_zeile(result, stats, fix_ids=set())
    assert note in row['Messstatus']
    assert 'Historie gekappt' in row['Messstatus']
    assert stats['quelle_trades_gekappt'] is True


def test_source_specific_history_note_has_precedence():
    result = ingest.metrics_zu_stats({'metrics': {'TradesCompletenessNote': 'new', 'CompletenessNote': 'legacy'}})
    assert result['quelle_trades_completeness_note'] == 'new'


@pytest.mark.parametrize('old_dd', [50.0, 0.05])
def test_admin_preserves_positive_limit_and_disabled_monthly_gate(old_dd):
    config.save_settings({'schranke_eq_dd_pct': old_dd, 'min_ertrag_pct_monat': 0.0,
                          'min_calmar_jahr': 3.0, 'top_n_export': 37})
    at = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30).run()
    at.switch_page('app_pages/admin.py').run()
    assert not at.exception
    assert at.number_input(key='admin_max_dd').value == old_dd
    assert at.number_input(key='admin_min_return').value == 0.0
    at.number_input(key='admin_max_dd').set_value(55.0)
    at.button(key='admin_risk_save').click().run()
    assert not at.exception
    saved = config.load_settings()
    assert saved['schranke_eq_dd_pct'] == 55.0
    assert saved['min_ertrag_pct_monat'] == 0.0
    assert saved['min_calmar_jahr'] == 3.0
    assert saved['top_n_export'] == 37


@pytest.mark.parametrize(('drawdown', 'expected'), [(49.9, '🟢'), (50.0, '🟢'), (50.1, '🔴')])
def test_fifty_percent_limit_uses_unrounded_drawdown(drawdown, expected):
    result = pipeline.ScanResult(id=900009, name='Boundary', forensik_vorhanden=True,
        score=2.0, dd_equity_pct=drawdown, equity_dd_rekonstruiert_pct=drawdown,
        ertrag_monat_geom_pct=10.0, cagr_jahr_pct=200.0)
    assert pipeline.ampel_for(result, {'schranke_eq_dd_pct': 50.0, 'min_calmar_jahr': 3.0})[0] == expected


@pytest.mark.parametrize('values', [
    {'equity_dd_rekonstruiert_pct': None},
    {'equity_dd_rekonstruiert_pct': None, 'equity_dd_rekon_roh_pct': 45.0},
    {'cagr_jahr_pct': 100.0},
    {'ertrag_monat_geom_pct': -1.0},
])
def test_fifty_percent_is_not_a_waiver_of_efficiency(values):
    data = dict(id=900009, name='Efficiency', forensik_vorhanden=True,
        dd_equity_pct=45.0, equity_dd_rekonstruiert_pct=45.0,
        ertrag_monat_geom_pct=10.0, cagr_jahr_pct=200.0)
    data.update(values)
    assert pipeline.ampel_for(pipeline.ScanResult(**data), {'schranke_eq_dd_pct': 50.0})[0] != '🟢'
