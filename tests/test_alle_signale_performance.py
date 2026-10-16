"""Übersichts-Laden spart Nebenarbeit, ohne gespeicherte Werte zu ändern."""
import pytest
from mqlkiscanner import db, katalog, pipeline, pdf_reports
from mqlkiscanner.alle_signale_ui import tabellen_zeile


def test_uebersicht_verwendet_snapshot_ohne_pdf_rendern(monkeypatch):
    db.init_db()
    db.upsert_signal(42, name='Probe', platform='MT5')
    db.store_analysis(42, 'tiefenanalyse', 'test', 0, 'Bestehender Bericht')
    rows, studien = db.list_catalog(), db.list_equity_studien()
    gerendert = []
    monkeypatch.setattr(pdf_reports, 'materialize_result_pdfs',
                        lambda result: gerendert.append(result.id))
    normal = pipeline.results_from_db()
    assert gerendert == [42]
    gerendert.clear()
    def unerwartet():
        raise AssertionError('Snapshot darf nicht erneut gelesen werden')
    monkeypatch.setattr(db, 'list_catalog', unerwartet)
    monkeypatch.setattr(db, 'list_equity_studien', unerwartet)
    fortschritt = []
    schnell = pipeline.results_from_db(
        catalog_rows=rows, studien=studien, materialize_pdfs=False,
        progress=lambda n, total: fortschritt.append((n, total)))
    assert vars(normal[0]) == vars(schnell[0])
    assert gerendert == []
    assert fortschritt == [(0, 1), (1, 1)]


def test_katalog_liest_artefakte_bulk_und_zaehlt_fortschritt(monkeypatch, tmp_path):
    db.init_db()
    db.katalog_upsert_many('vant', [dict(signal_id=i, name=str(i),
        platform='vantage', version='vantage') for i in range(1, 4)])
    monkeypatch.setattr(db, 'list_quellen', lambda: [dict(id=7, kuerzel='vant')])
    trades = tmp_path / 'trades.csv'
    trades.write_text('test')
    artefakte = {(7, i, 'vantage', 'trades'): dict(path=str(trades), sha256=str(i))
                 for i in range(1, 4)}
    bulk_aufrufe = []
    def bulk():
        bulk_aufrufe.append(1)
        return artefakte
    monkeypatch.setattr(db, 'list_quellen_artefakte', bulk)
    def einzeln(*args):
        raise AssertionError('Keine Einzelabfragen je Signal')
    monkeypatch.setattr(db, 'get_quellen_artefakt', einzeln)
    fortschritt = []
    resultate, _ = katalog.katalog_resultate(
        gescannt={2}, studien={},
        progress=lambda n, total: fortschritt.append((n, total)))
    assert {r.id for r in resultate} == {1, 3}
    assert all(r.trades_path == str(trades) for r in resultate)
    assert len(bulk_aufrufe) == 1
    assert fortschritt[0] == (0, 3)
    assert fortschritt[-1] == (3, 3)


def test_bulk_index_enthaelt_alle_identitaetsbestandteile():
    db.init_db()
    quelle = db.add_quelle('vant', 'Vantage', 'http://localhost:8092')
    db.store_quellen_artefakt(quelle, 42, 'mql4', 'trades', 'sha-a', 'a.csv')
    db.store_quellen_artefakt(quelle, 42, 'mql5', 'trades', 'sha-b', 'b.csv')
    index = db.list_quellen_artefakte()
    assert index[(quelle, 42, 'mql4', 'trades')]['sha256'] == 'sha-a'
    assert index[(quelle, 42, 'mql5', 'trades')]['sha256'] == 'sha-b'


def test_tabellenzeilen_nutzen_gemeinsame_fix_ids(monkeypatch):
    from mqlkiscanner import alle_signale_ui
    def unerwartet():
        raise AssertionError('Einstellungen nicht je Zeile laden')
    monkeypatch.setattr(alle_signale_ui, '_fix_ids', unerwartet)
    assert tabellen_zeile(pipeline.ScanResult(id=42, name='Probe'), {},
                          fix_ids={42})['Fix'] == '📌 FIX'


def test_seite_zeigt_gezählte_phasen_und_geschaetzte_restzeit(monkeypatch):
    from pathlib import Path
    from itertools import count
    from time import monotonic
    from types import SimpleNamespace
    import re
    from streamlit.delta_generator import DeltaGenerator
    from streamlit.testing.v1 import AppTest

    texte = []
    original_caption = DeltaGenerator.caption
    def caption(self, body, *args, **kwargs):
        texte.append(str(body))
        return original_caption(self, body, *args, **kwargs)
    monkeypatch.setattr(DeltaGenerator, 'caption', caption)
    rows = [dict(signal_id=1, stats={}), dict(signal_id=2, stats={})]
    monkeypatch.setattr(db, 'list_catalog', lambda: rows)
    monkeypatch.setattr(db, 'list_equity_studien', lambda: {})
    monkeypatch.setattr(db, 'katalog_sync_status', lambda: {'vant': dict(anzahl=2)})
    def workflow(**kwargs):
        assert kwargs['materialize_pdfs'] is False
        assert kwargs['catalog_rows'] is rows
        ticks = count(monotonic() + 1, 0.5)
        kwargs['progress'].__globals__['time'] = SimpleNamespace(
            monotonic=lambda: next(ticks))
        for n in range(3):
            kwargs['progress'](n, 2)
        return [pipeline.ScanResult(id=i, name=str(i)) for i in (1, 2)]
    monkeypatch.setattr(pipeline, 'results_from_db', workflow)
    monkeypatch.setattr(katalog, 'katalog_resultate', lambda **kwargs: ([], {}))
    seite = Path(__file__).resolve().parents[1] / 'app_pages' / 'alle_signale.py'
    at = AppTest.from_file(str(seite), default_timeout=30).run()
    assert not at.exception
    assert any('Workflow-Signale aufbereiten: 1/2' in text for text in texte)
    assert any(re.search(r'2/2 · vergangen [\d.]+ s · Rest dieser Phase ≈ 0.0 s', text)
               and '(Schätzung)' in text for text in texte)
    assert any('Datenbank lesen' in text and 'Restzeit noch unbekannt' in text
               for text in texte)
    assert any('Übersicht geladen in' in caption.value for caption in at.caption)


@pytest.mark.parametrize('study_sha,trade_sha,initial,expected_basis', [
    ('same', 'same', None, 10_000.0),
    ('old', 'new', None, None),
    ('', 'same', None, None),
    ('same', '', None, None),
    ('same', 'same', 20_000.0, 20_000.0),
])
def test_virtuelle_studienbasis_nur_fuer_zugehoerige_trades(
        monkeypatch, tmp_path, study_sha, trade_sha, initial, expected_basis):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from mqlkiscanner import signal_statistik

    csv = tmp_path / 'dino.csv'
    csv.write_text(
        'Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n'
        '2026.01.05 10:00:00;Buy;0.1;EURUSD;1.1;0.1;2026.01.05 11:00:00;1.101;0;0;100\n'
        '2026.02.05 10:00:00;Buy;0.1;EURUSD;1.1;0.1;2026.02.05 11:00:00;1.102;0;0;200\n',
        encoding='utf-8')
    stats = dict(initial_deposit_usd=initial, kapitalbasis_virtual_usd=None,
                 regression_test=tmp_path.name)
    result = pipeline.ScanResult(id=1286742, name='DINO',
        trades_path=str(csv), trades_sha256=trade_sha)
    monkeypatch.setattr(db, 'list_catalog', lambda: [dict(signal_id=result.id, stats=stats)])
    monkeypatch.setattr(db, 'list_equity_studien', lambda: {
        result.id: dict(virtuell=True, trades_sha=study_sha)})
    monkeypatch.setattr(db, 'katalog_sync_status', lambda: {'vant': dict(anzahl=1)})
    monkeypatch.setattr(pipeline, 'results_from_db', lambda **kwargs: [result])
    monkeypatch.setattr(katalog, 'katalog_resultate', lambda **kwargs: ([], {}))
    computed = []
    original = signal_statistik.berechne
    def berechne(path, basis_stats):
        value = original(path, basis_stats)
        computed.append(value)
        return value
    monkeypatch.setattr(signal_statistik, 'berechne', berechne)
    page = Path(__file__).resolve().parents[1] / 'app_pages' / 'alle_signale.py'
    at = AppTest.from_file(str(page), default_timeout=30).run()
    assert not at.exception
    assert computed and computed[-1]['kapitalbasis_usd'] == expected_basis
    geom = at.dataframe[0].value.iloc[0]['Geom. %/M']
    if expected_basis is None:
        assert geom != geom  # numeric empty cell / NaN
    else:
        assert geom > 0
    if initial is not None:
        assert stats['kapitalbasis_virtual_usd'] is None
