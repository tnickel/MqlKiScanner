"""Concrete source collisions remain isolated in every storage family."""
import sqlite3
from contextlib import contextmanager

import pytest

from mqlkiscanner import db
from mqlkiscanner.agenten import dossier, journal
from mqlkiscanner.signal_identity import AmbiguousSignalIdentity, IdentityError, identity_key, stable_identity_key


@pytest.fixture
def pair(tmp_path):
    path=tmp_path/'same.csv'
    path.write_text('identical bytes',encoding='utf8')
    for source in ('mql5','vant'):
        db.store_scan_result(42,{'quelle':source,'name':source,'platform':'MT5'},str(path),{'owner':source})
    return db.resolve_identity(42,quelle='mql5'),db.resolve_identity(42,quelle='vant')


def test_equal_external_id_platform_and_sha_have_separate_references(pair):
    a,b=pair
    assert a.signal_ref!=b.signal_ref and a.quellen_uid!=b.quellen_uid
    rows=db.list_catalog()
    assert {r['quelle'] for r in rows}=={'mql5','vant'}
    assert len({r['trades_sha256'] for r in rows})==1
    assert {r['forensik']['owner'] for r in rows}=={'mql5','vant'}
    with pytest.raises(AmbiguousSignalIdentity): db.get_signal(42)
    assert db.get_signal(42,signal_ref=a.signal_ref)['name']=='mql5'
    with pytest.raises(IdentityError): db.get_signal(42,quelle='vant',signal_ref=a.signal_ref)
    with pytest.raises(IdentityError): db.get_signal(99,signal_ref=a.signal_ref)


def test_all_children_keep_their_owner(pair,tmp_path):
    for source in ('mql5','vant'):
        db.store_equity_studie(42,'same-sha',{'owner':source},quelle=source)
        db.store_history_points(42,'mql5',[{'timestamp':source,'subscribers':3}],quelle=source)
        db.setze_kommentar(42,source,quelle=source)
        db.setze_markierung(42,source,quelle=source)
        db.store_downloader_report(42,'mql5',source,'path',quelle=source)
        db.store_analysis(42,'gesamtbericht','offline',1,source,basis='same-basis',quelle=source)
        db.store_ampel_verlauf(42,'same-time','full',source,None,'',{},signal_quelle=source)
        db.store_ampel_wechsel(42,'same-time','full',None,source,True,'neutral',[],signal_quelle=source)
    for source in ('mql5','vant'):
        assert db.get_equity_studie(42,quelle=source)['report']['owner']==source
        assert db.get_history(42,quelle=source)[0]['ts']==source
        assert db.get_kommentar(42,quelle=source)==source
        assert db.list_downloader_reports(42,quelle=source)[0]['name']==source
        assert db.get_latest_analysis(42,'gesamtbericht',quelle=source)['text']==source
        assert db.get_last_ampel_verlauf(42,quelle=source)['ampel']==source
        assert db.list_ampel_wechsel(signal_id=42,quelle=source)[0]['ampel_neu']==source
    assert set(db.list_equity_studien(identitaeten=True))=={('mql5',42),('vant',42)}
    assert db.list_equity_studien()=={}
    assert db.list_markierungen(identitaeten=True)=={('mql5',42):'mql5',('vant',42):'vant'}
    assert db.list_kommentare(identitaeten=True)=={('mql5',42):'mql5',('vant',42):'vant'}
    assert db.downloader_report_counts([('mql5',42),('vant',42)])=={('mql5',42):1,('vant',42):1}
    for read in (db.get_equity_studie,db.get_history,db.get_kommentar,db.list_downloader_reports,db.get_last_ampel_verlauf):
        with pytest.raises(AmbiguousSignalIdentity): read(42)
    with db._connect() as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_dossier_and_journal_cannot_cross_link(pair):
    for source in ('mql5','vant'):
        assert dossier.profil_speichern(42,source,'offline',{},quelle=source)==1
        assert dossier.profil_speichern(42,source+' v2','offline',{},quelle=source)==2
        delta=dossier.delta_speichern(42,None,'same-sha',1,{'owner':source},quelle=source)
        run=journal.lauf_starten('betreuer','gui',42,signal_quelle=source)
        step=journal.schritt_protokollieren(run,'betreuer','check',status='ok')
        dossier.beobachtung_speichern(42,'KONFORM',source,delta,step,quelle=source)
        if source=='mql5': foreign_delta,foreign_step=delta,step
    for source in ('mql5','vant'):
        assert dossier.profil_lesen(42,quelle=source)['profil_text']==source+' v2'
        assert len(dossier.profil_historie(42,quelle=source))==2
        assert dossier.beobachtungen_lesen(42,quelle=source)[0]['text']==source
        assert dossier.deltas_lesen(42,quelle=source)[0]['delta']['owner']==source
    for delta,step in ((foreign_delta,None),(None,foreign_step)):
        with pytest.raises(IdentityError):
            dossier.beobachtung_speichern(42,'KONFORM','wrong owner',delta,step,quelle='vant')
    with pytest.raises(AmbiguousSignalIdentity): dossier.profil_lesen(42)


@pytest.mark.parametrize('entrypoint',['workflow','catalog'])
@pytest.mark.parametrize('direction',[('MT4','MT5'),('MT5','MT4')])
def test_same_owner_platform_conflicts_rollback_whole_batch(entrypoint,direction):
    first,second=direction
    if entrypoint=='workflow': db.upsert_signal(42,quelle='mql5',platform=first)
    else: db.katalog_upsert_many('mql5',[{'signal_id':42,'platform':first}])
    before=db.katalog_list(),db.list_catalog()
    with pytest.raises(IdentityError,match='Plattform'):
        db.katalog_upsert_many('mql5',[{'signal_id':99,'platform':'MT5'}, {'signal_id':42,'platform':second}])
    assert (db.katalog_list(),db.list_catalog())==before
    assert db.resolve_identity(99,quelle='mql5') is None
    with pytest.raises(IdentityError,match='Plattform'): db.upsert_signal(42,quelle='mql5',platform=second)
    db.upsert_signal(42,quelle='vant',platform=second) # different owner is independent


def test_source_rename_archive_and_explicit_reactivation(pair):
    a,b=pair
    qid=db.add_quelle('vant','Vantage','http://localhost:1',quellen_uid=b.quellen_uid)
    db.set_signal_fix(42,quelle='vant')
    db.update_quelle(qid,kuerzel='new-vantage')
    assert db.resolve_identity(42,quelle='vant')==db.resolve_identity(42,quelle='new-vantage')
    assert identity_key({'quelle':'vant','id':42})==('new-vantage',42)
    assert stable_identity_key({'quelle':'vant','id':42,'signal_ref':b.signal_ref})==('ref',b.signal_ref)
    assert db.list_signal_fixierungen(identitaeten=True)=={('new-vantage',42)}
    db.delete_quelle(qid)
    with pytest.raises(IdentityError,match='Reservierter'): db.add_quelle('new-vantage','Other','http://localhost:2')
    assert db.add_quelle('new-vantage','Restored','http://localhost:2',quellen_uid=b.quellen_uid)==qid
    assert db.get_signal(42,quelle='new-vantage')['signal_ref']==b.signal_ref


def test_bulk_counts_query_count_does_not_grow_per_signal(monkeypatch):
    for external in range(30):
        db.resolve_identity(external,quelle='mql5',create=True)
    queries=[]
    original=db._connect
    @contextmanager
    def traced():
        with original() as conn:
            conn.set_trace_callback(queries.append)
            yield conn
    monkeypatch.setattr(db,'_connect',traced)
    assert len(db.downloader_report_counts([('mql5',i) for i in range(30)]))==30
    assert len([q for q in queries if q.startswith('SELECT')])<=4
