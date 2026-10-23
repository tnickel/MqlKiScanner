"""Copy migration keeps ownership, row balances, audit text and rollback input."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from mqlkiscanner import db, identity_migration as migration
from mqlkiscanner.signal_identity import IdentityMigrationRequired, AmbiguousSignalIdentity


def legacy_database(path, *, empty_source=None, collisions=False):
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE signals(signal_id INTEGER PRIMARY KEY,name TEXT,platform TEXT,quelle TEXT);
            CREATE TABLE katalog_signale(quelle TEXT,signal_id INTEGER,name TEXT,platform TEXT,PRIMARY KEY(quelle,signal_id));
            CREATE TABLE forensik(signal_id INTEGER PRIMARY KEY,json TEXT);
            CREATE TABLE analyses(id INTEGER PRIMARY KEY,signal_id INTEGER,kind TEXT,text TEXT);
            CREATE TABLE signal_kommentare(signal_id INTEGER PRIMARY KEY,kommentar TEXT);
            CREATE TABLE equity_studien(signal_id INTEGER PRIMARY KEY,trades_sha TEXT,json TEXT,forensics_version INTEGER);
            CREATE TABLE ampel_verlauf(signal_id INTEGER,ts TEXT,quelle TEXT,ampel TEXT,PRIMARY KEY(signal_id,ts));
            CREATE TABLE datenquellen(id INTEGER PRIMARY KEY,kuerzel TEXT,base_url TEXT);
            CREATE TABLE agenten_laeufe(id INTEGER PRIMARY KEY,rolle TEXT,quelle TEXT,start TEXT,status TEXT,signal_id INTEGER);
            CREATE TABLE agenten_schritte(id INTEGER PRIMARY KEY,lauf_id INTEGER,ts TEXT,rolle TEXT,schritt TEXT,status TEXT);
        """)
        conn.execute("INSERT INTO signals VALUES(42,'Legacy','MT5',?)",(empty_source,))
        conn.execute("INSERT INTO forensik VALUES(42,?)",('{"verbatim": "Legacy payload"}',))
        conn.execute("INSERT INTO analyses VALUES(5,0,'portfolio','Portfolio original')")
        conn.execute("INSERT INTO analyses VALUES(6,999,'gesamtbericht','Orphan original')")
        conn.execute("INSERT INTO signal_kommentare VALUES(42,'Original comment')")
        conn.execute("INSERT INTO equity_studien VALUES(42,'same-sha','{}',19)")
        conn.execute("INSERT INTO ampel_verlauf VALUES(42,'2026-10-18','full','gruen')")
        conn.execute("INSERT INTO datenquellen VALUES(7,'mql5','http://localhost:1')")
        conn.execute("INSERT INTO agenten_laeufe VALUES(8,'betreuer','daemon','2026-10-18','ok',42)")
        conn.execute("INSERT INTO agenten_schritte VALUES(9,8,'2026-10-18','betreuer','x','ok')")
        conn.execute("INSERT INTO katalog_signale VALUES('mql5',88,'Only catalog','MT5')")
        if collisions:
            conn.execute("INSERT INTO katalog_signale VALUES('vant',42,'Other source','MT5')")


@pytest.mark.parametrize("empty",[None,""," "])
def test_copy_migration_normalizes_only_empty_legacy_source(tmp_path,monkeypatch,empty):
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source,empty_source=empty)
    before=source.read_bytes()
    report=migration.migrate_copy(source,target,verify_files=False)
    assert source.read_bytes()==before
    assert report['activated'] is False
    assert report['integrity_check']=='ok' and report['foreign_key_errors']==0
    assert all(item['before']==item['migrated']+item['quarantined'] for item in report['tables'].values())
    assert report['tables']['analyses']=={'before':2,'migrated':1,'quarantined':1}
    monkeypatch.setattr(db,'DB_PATH',target)
    assert db.get_signal(42,quelle='mql5')['name']=='Legacy'
    assert db.get_kommentar(42,quelle='mql5')=='' # current owner is no historical ownership proof
    assert db.get_signal(88,quelle='mql5') is None
    assert db.resolve_identity(88,quelle='mql5') is not None
    with sqlite3.connect(target) as conn:
        raw={row[0]:json.loads(row[1]) for row in conn.execute('SELECT ursprung_tabelle,datensatz_json FROM migration_quarantaene')}
        assert raw['ampel_verlauf']['quelle']=='full'
        assert raw['agenten_laeufe']['quelle']=='daemon'
        orphan=raw['analyses']
        assert orphan['signal_id']==999 and orphan['text']=='Orphan original'
        assert raw['agenten_schritte']['id']==9
    assert Path(report['backup']['path']).is_file()
    assert hashlib.sha256(Path(report['backup']['path']).read_bytes()).hexdigest()==report['backup']['sha256']


def test_collision_quarantines_unqualified_children_without_guessing_from_sha_or_platform(tmp_path,monkeypatch):
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source,collisions=True)
    report=migration.migrate_copy(source,target,verify_files=False)
    for table in ('equity_studien','signal_kommentare','ampel_verlauf','agenten_laeufe','agenten_schritte'):
        assert report['tables'][table]['quarantined']==1
    assert report['tables']['forensik']['migrated']==1 # original workflow parent proves its owner
    monkeypatch.setattr(db,'DB_PATH',target)
    assert db.list_catalog()[0]['forensik']['verbatim']=='Legacy payload'
    with pytest.raises(AmbiguousSignalIdentity): db.get_signal(42)
    assert db.get_signal(42,quelle='vant') is None
    assert db.get_equity_studie(42,quelle='mql5') is None
    assert db.get_equity_studie(42,quelle='vant') is None
    assert report['foreign_key_errors']==0


def test_one_current_catalog_owner_is_not_a_historical_child_source_proof(tmp_path):
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source)
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE equity_studien SET signal_id=88') # only current catalog owner, no workflow
    report=migration.migrate_copy(source,target,verify_files=False)
    assert report['tables']['equity_studien']['quarantined']==1
    assert report['tables']['signal_kommentare']['quarantined']==1 # workflow alone also is insufficient
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT COUNT(*) FROM equity_studien').fetchone()[0]==0
        reason=conn.execute("SELECT grund FROM migration_quarantaene WHERE ursprung_tabelle='equity_studien'").fetchone()[0]
        assert 'Quellenbeleg fehlt' in reason


def test_live_init_rejects_partial_legacy_without_any_writes(tmp_path,monkeypatch):
    source=tmp_path/'partial.db'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE analyses(signal_id INTEGER,text TEXT)')
    before=source.read_bytes()
    monkeypatch.setattr(db,'DB_PATH',source)
    with pytest.raises(IdentityMigrationRequired): db.init_db()
    assert source.read_bytes()==before
    assert not Path(str(source)+'-wal').exists()


def test_half_initialized_v2_fails_closed(tmp_path,monkeypatch):
    source=tmp_path/'partial.db'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE signal_identitaeten(signal_ref INTEGER)')
        conn.execute('PRAGMA user_version=2')
    monkeypatch.setattr(db,'DB_PATH',source)
    with pytest.raises(IdentityMigrationRequired): db.init_db()


def test_copy_does_not_overwrite_or_activate_and_new_writers_reject_old_sql(tmp_path,monkeypatch):
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source)
    migration.migrate_copy(source,target,verify_files=False)
    before=target.read_bytes()
    with pytest.raises(ValueError): migration.migrate_copy(source,target,verify_files=False)
    assert target.read_bytes()==before
    monkeypatch.setattr(db,'DB_PATH',target)
    db.init_db()
    with db._connect() as conn:
        with pytest.raises(sqlite3.OperationalError,match='signal_id'):
            conn.execute('INSERT INTO signals(signal_id,name) VALUES(42,\'old writer\')')


def test_sqlite_backup_includes_committed_wal_pages(tmp_path):
    source,target=tmp_path/'legacy.db',tmp_path/'backup.db'
    with sqlite3.connect(source) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE evidence(value TEXT)')
        conn.execute('INSERT INTO evidence VALUES(\'committed WAL\')')
        conn.commit()
        migration.backup_database(source,target)
        with sqlite3.connect(target) as backup:
            assert backup.execute('SELECT value FROM evidence').fetchone()[0]=='committed WAL'


def test_unattributed_pins_only_use_unique_current_owner_and_preserve_unknowns(tmp_path,monkeypatch):
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source,collisions=True)
    with sqlite3.connect(source) as conn:
        conn.execute("INSERT INTO katalog_signale VALUES('vant',77,'Foreign pin','MT5')")
    report=migration.migrate_copy(source,target,verify_files=False,settings={'fix_signal_ids':[42,77,999]})
    assert report['legacy_pins']=={'before':3,'migrated':1,'quarantined':2}
    monkeypatch.setattr(db,'DB_PATH',target)
    assert db.list_signal_fixierungen(identitaeten=True)=={('vant',77)}
    assert db.resolve_identity(999,quelle='mql5') is None


def test_explicit_historical_source_allows_child_without_using_current_uniqueness(tmp_path,monkeypatch):
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source,collisions=True)
    with sqlite3.connect(source) as conn:
        conn.execute('ALTER TABLE signal_kommentare ADD COLUMN signal_quelle TEXT')
        conn.execute("UPDATE signal_kommentare SET signal_quelle='vant'")
    report=migration.migrate_copy(source,target,verify_files=False)
    assert report['tables']['signal_kommentare']['migrated']==1
    monkeypatch.setattr(db,'DB_PATH',target)
    assert db.get_kommentar(42,quelle='vant')=='Original comment'
    assert db.get_kommentar(42,quelle='mql5')==''


@pytest.mark.parametrize('autoincrement',[True,False])
def test_quarantined_audit_ids_are_never_reused_by_next_insert(tmp_path,monkeypatch,autoincrement):
    from mqlkiscanner.agenten import dossier
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source)
    with sqlite3.connect(source) as conn:
        extra='AUTOINCREMENT' if autoincrement else ''
        conn.execute(f'CREATE TABLE trade_deltas(id INTEGER PRIMARY KEY {extra},signal_id INTEGER)')
        conn.execute('INSERT INTO trade_deltas VALUES(99,42)')
    report=migration.migrate_copy(source,target,verify_files=False)
    assert report['tables']['trade_deltas']['quarantined']==1
    assert report['sequence_highwatermarks_preserved']
    monkeypatch.setattr(db,'DB_PATH',target)
    assert dossier.delta_speichern(42,None,'new-sha',1,{},quelle='mql5')==100


@pytest.mark.parametrize('ledger_flag_present',[True,False])
def test_quarantined_journal_costs_keep_daily_monthly_and_reservation_totals(tmp_path,monkeypatch,ledger_flag_present):
    from datetime import datetime
    from mqlkiscanner.agenten import budget,journal
    from mqlkiscanner.llm.client import LlmBudgetError
    source,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    legacy_database(source)
    with sqlite3.connect(source) as conn:
        conn.execute('ALTER TABLE agenten_schritte ADD COLUMN tokens INTEGER')
        conn.execute('ALTER TABLE agenten_schritte ADD COLUMN prompt TEXT')
        conn.execute('ALTER TABLE agenten_schritte ADD COLUMN budget_ledger INTEGER DEFAULT 0')
        conn.execute("UPDATE agenten_schritte SET ts='2026-10-16 12:00:00',tokens=13,prompt='known request' WHERE id=9")
        conn.execute("INSERT INTO agenten_laeufe VALUES(10,'dirigent','daemon','2026-10-16','ok',NULL)")
        for step,run,tokens,prompt,flag in [(10,8,777,'ledger mirror',1),(11,8,0,'zero tokens',0),
                                           (12,8,500,None,0),(13,10,7,'global cost',0)]:
            conn.execute("INSERT INTO agenten_schritte VALUES(?,?,'2026-10-16 12:00:00','legacy','test','ok',?,?,?)",
                         (step,run,tokens,prompt,flag))
        conn.executescript(budget._SCHEMA)
        conn.execute("INSERT INTO agenten_budget_versuche(id,tag,monat,reserviert,tokens,abgeschlossen) "
                     "VALUES('paid','2026-10-16','2026-10',17,17,1)")
        conn.execute("INSERT INTO agenten_budget_versuche(id,tag,monat,reserviert,tokens,abgeschlossen) "
                     "VALUES('open','2026-10-17','2026-10',30,0,0)")
        if not ledger_flag_present:
            conn.execute('DELETE FROM agenten_schritte WHERE id=10') # a ledger mirror requires its explicit flag
            conn.execute('ALTER TABLE agenten_schritte DROP COLUMN budget_ledger')
    report=migration.migrate_copy(source,target,verify_files=False)
    evidence=report['budget_preservation']
    assert evidence['unchanged'] and evidence['before']==evidence['after']
    assert evidence['after']['2026-10-16']=={'spent':37,'used_or_reserved':37}
    assert evidence['after']['2026-10']=={'spent':37,'used_or_reserved':67}
    assert evidence['cost_receipts']==(4 if ledger_flag_present else 3)
    monkeypatch.setattr(db,'DB_PATH',target)
    monkeypatch.setattr(journal,'_heute',lambda:'2026-10-16')
    monkeypatch.setattr(journal,'_monat',lambda:'2026-10')
    class Clock:
        @staticmethod
        def now(): return datetime(2026,10,16,12)
    monkeypatch.setattr(budget,'datetime',Clock)
    assert journal.tokens_heute()==journal.tokens_monat()==37
    limits={'agenten_tagesbudget_tokens':40,'agenten_monatsbudget_tokens':100}
    with pytest.raises(LlmBudgetError): budget.reserve(limits,4,'offline','must not exceed restored costs')
    ticket=budget.reserve(limits,3,'offline','fits')
    with pytest.raises(LlmBudgetError): budget.reserve(limits,1,'offline','reserved cost also counts')
    budget.settle(ticket,2,'offline','ok')
    assert journal.tokens_heute()==journal.tokens_monat()==39
    with db._connect() as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('SELECT MAX(schritt_id) FROM agenten_budget_altkosten').fetchone()[0]==12


@pytest.mark.parametrize('defect',['missing_unique','partial_unique','missing_pk','nullable_owner'])
def test_schema_guard_rejects_v2_without_complete_identity_constraints(tmp_path,monkeypatch,defect):
    source=tmp_path/'malformed_v2.db'
    schema=db._SCHEMA
    if defect in ('missing_unique','partial_unique'):
        schema=schema.replace('UNIQUE(quellen_uid, externe_id)','CHECK(1)')
    elif defect=='missing_pk':
        schema=schema.replace('signal_ref INTEGER PRIMARY KEY AUTOINCREMENT','signal_ref INTEGER')
    else:
        schema=schema.replace('quellen_uid TEXT NOT NULL REFERENCES quellen_identitaeten(quellen_uid)',
                              'quellen_uid TEXT REFERENCES quellen_identitaeten(quellen_uid)')
    with sqlite3.connect(source) as conn:
        conn.executescript(schema)
        conn.execute('PRAGMA user_version=2')
        if defect=='partial_unique':
            conn.execute('CREATE UNIQUE INDEX partial_owner ON signal_identitaeten(quellen_uid,externe_id) WHERE externe_id>0')
    before=source.read_bytes()
    monkeypatch.setattr(db,'DB_PATH',source)
    with pytest.raises(IdentityMigrationRequired): db.init_db()
    assert source.read_bytes()==before
    with pytest.raises(IdentityMigrationRequired): migration.migrate_copy(source,tmp_path/'refused.db',verify_files=False)
