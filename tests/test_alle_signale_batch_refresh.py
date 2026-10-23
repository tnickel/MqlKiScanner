"""Studienfortschritt muss die Tabelle ohne neuen Batchstart aktualisieren."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from mqlkiscanner import alle_signale_ui as ui
from mqlkiscanner import db, katalog, scan_worker


def _run():
    return SimpleNamespace(
        workflow={'typ': 'studien_batch'}, thread=None,
        control={'gerechnet': 0, 'fertig': False, 'gesamt': 2, 'aktuell': 0,
                 'uebersprungen': 0, 'fehler': [], 'summary': ''})


def _stand(run, jetzt=100.0):
    return {**ui.studien_batch_tabellenstand(run), 'geladen_am': jetzt}


def test_sitzung_behaelt_batch_nach_registry_freigabe():
    state, run = {}, _run()
    assert ui.studien_batch_merken(state, run) is run
    assert ui.studien_batch_merken(state, None) is run
    other = SimpleNamespace(workflow={'typ': 'workflow'})
    assert ui.studien_batch_merken(state, other) is run
    newer = _run()
    assert ui.studien_batch_merken(state, newer) is newer


def test_nur_neue_gespeicherte_studien_loesen_gedrosselten_refresh_aus():
    run = _run()
    stand = _stand(run)
    run.control.update(aktuell=1, uebersprungen=1)
    assert not ui.studien_batch_refresh_noetig(run, stand, jetzt=120.0)
    run.control['gerechnet'] = 1
    assert not ui.studien_batch_refresh_noetig(run, stand, jetzt=114.0)
    assert ui.studien_batch_refresh_noetig(run, stand, jetzt=115.0)
    assert not ui.studien_batch_refresh_noetig(run, _stand(run, 115.0), jetzt=140.0)


def test_abschluss_wird_sofort_je_sitzung_einmal_uebernommen():
    run = _run()
    first, second = _stand(run), _stand(run)
    # Ein Alt-Flag eines anderen Clients darf keine Sitzung blockieren.
    run.control.update(fertig=True, uebernommen=True)
    assert ui.studien_batch_refresh_noetig(run, first, jetzt=101.0)
    first = _stand(run, 101.0)
    assert not ui.studien_batch_refresh_noetig(run, first, jetzt=102.0)
    assert ui.studien_batch_refresh_noetig(run, second, jetzt=102.0)
    assert not ui.studien_batch_refresh_noetig(run, _stand(run), jetzt=103.0)


def test_erstmals_im_fragment_entdeckter_batch_laesst_tabelle_nachladen():
    run = _run()
    assert ui.studien_batch_refresh_noetig(run, {}, jetzt=100.0)
    assert not ui.studien_batch_refresh_noetig(None, {}, jetzt=100.0)


def test_seite_laesst_abschluss_nach_registry_freigabe_in_tabelle_einfliessen(monkeypatch):
    """Abschluss zwischen DB-Lesen und Fragmenttick darf nicht verloren gehen."""
    from streamlit.testing.v1 import AppTest

    db.init_db()
    db.upsert_signal(31, name='Neue Studie', platform='vantage', quelle='vant')
    monkeypatch.setattr(db, 'katalog_sync_status', lambda: {
        'vant': {'gelaufen_am': '2026-10-17', 'anzahl': 1, 'fehler': None}})
    monkeypatch.setattr(katalog, 'katalog_resultate', lambda **kwargs: ([], {}))
    run, calls = _run(), []

    def active_run():
        calls.append(True)
        if len(calls) == 1:
            return run
        if len(calls) == 2:
            db.store_equity_studie(
                31, '', {'verlaesslich': True, 'equity_dd_pct': 9.0,
                         'equity_dd_pct_raw': 9.0, 'equity_dd_usd': 800.0,
                         'test': 'equity_rekonstruktion'},
                cagr_jahr_pct=27.0, ertrag_monat_geom_pct=2.0,
                dd_usd=800.0, basislos=False, quelle="vant")
            run.control.update(fertig=True, gerechnet=1, aktuell=2,
                               summary='1 gerechnet · 1 übersprungen · 0 Fehler')
        return None

    monkeypatch.setattr(scan_worker, 'active_run', active_run)
    # Kein Test darf einen echten Lauf starten oder MetaTrader öffnen.
    monkeypatch.setattr(scan_worker, 'start', lambda *args, **kwargs: pytest.fail('Neuer Batch'))
    page = Path(__file__).resolve().parents[1] / 'app_pages' / 'alle_signale.py'
    at = AppTest.from_file(str(page), default_timeout=30).run()
    assert not at.exception, at.exception
    row = at.dataframe[0].value.iloc[0]
    assert row['True-DD USD'] == pytest.approx(800.0)
    assert row['True-DD %'] == pytest.approx(9.0)
    assert row['TrueRetDD'] == pytest.approx(3.0)
    assert any('Studien-Batch beendet' in item.value for item in at.info)
    assert 'uebernommen' not in run.control
    # Der erneute normale Seitenlauf muss ohne Rerun-Schleife fertig werden.
    at.run()
    assert not at.exception, at.exception
    assert at.dataframe[0].value.iloc[0]['True-DD USD'] == pytest.approx(800.0)
