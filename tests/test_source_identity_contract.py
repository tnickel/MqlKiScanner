"""The low-level write API must enforce the scan's explicit source contract."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier

import pytest

from mqlkiscanner import db, identity_migration
from mqlkiscanner.signal_identity import AmbiguousSignalIdentity


@pytest.mark.parametrize("source", [None, "", " ", True, 7])
def test_direct_upsert_cannot_update_existing_identity_without_valid_source(source):
    db.init_db()
    db.upsert_signal(123, name="Original", platform="MT5", quelle="pelik",
                     stats={"original": True})
    before = db.get_signal(123)
    with pytest.raises(ValueError, match="ID-Kollision abgewehrt"):
        db.upsert_signal(123, name="Unattributed replacement", platform="MT4",
                         quelle=source, stats={"foreign": True})
    assert db.get_signal(123) == before


def test_direct_upsert_allows_legacy_creation_and_explicit_same_source_update():
    db.init_db()
    db.upsert_signal(123, name="Legacy creation")
    assert db.get_signal(123)["quelle"] == "mql5"
    db.upsert_signal(123, name="Attributed update", quelle="mql5")
    assert db.get_signal(123)["name"] == "Attributed update"
    db.upsert_signal(123, name="Other source", quelle="vant")
    assert db.get_signal(123, quelle="mql5")["name"] == "Attributed update"
    assert db.get_signal(123, quelle="vant")["name"] == "Other source"
    with pytest.raises(AmbiguousSignalIdentity):
        db.get_signal(123)



@pytest.mark.parametrize("api", ["upsert_signal", "store_scan_result"])
@pytest.mark.parametrize("legacy_source", [None, "", " "], ids=["null", "empty", "space"])
def test_legacy_empty_source_migrates_to_mql5_and_other_owner_stays_separate(api, legacy_source, tmp_path, monkeypatch):
    import sqlite3
    legacy,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    with sqlite3.connect(legacy) as conn:
        conn.execute("CREATE TABLE signals(signal_id INTEGER PRIMARY KEY,name TEXT,quelle TEXT)")
        conn.execute("INSERT INTO signals VALUES(123,'Original',?)",(legacy_source,))
    identity_migration.migrate_copy(legacy,target,verify_files=False)
    monkeypatch.setattr(db,'DB_PATH',target)
    def update(source,name):
        if api=='upsert_signal': db.upsert_signal(123,name=name,quelle=source)
        else: db.store_scan_result(123,{'name':name,'quelle':source})
    update('vant','Foreign independent signal')
    assert db.get_signal(123,quelle='mql5')['name']=='Original'
    assert db.get_signal(123,quelle='vant')['name']=='Foreign independent signal'
    update('mql5','Explicit MQL5 update')
    assert db.get_signal(123,quelle='mql5')['name']=='Explicit MQL5 update'


@pytest.mark.parametrize("api", ["upsert_signal", "store_scan_result"])
def test_nonempty_padded_source_keeps_exact_update_compatibility(api):
    db.init_db()
    source = " pelik "

    def write(name):
        payload = {"name": name, "quelle": source}
        if api == "upsert_signal":
            db.upsert_signal(123, **payload)
        else:
            db.store_scan_result(123, payload)

    write("Original")
    assert db.get_signal(123)["quelle"] == source
    write("Exact source update")
    after = db.get_signal(123)
    assert after["quelle"] == source
    assert after["name"] == "Exact source update"


@pytest.mark.parametrize("source", ["", " ", True, 7])
def test_direct_upsert_rejects_invalid_source_on_creation(source):
    db.init_db()
    with pytest.raises(ValueError, match="Signalquelle"):
        db.upsert_signal(123, quelle=source)
    assert db.get_signal(123) is None


def test_existing_connection_cannot_bypass_low_level_source_guard():
    db.init_db()
    db.upsert_signal(123, name="Original", quelle="mql5")
    with db._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="explizite Quelle"):
            db.upsert_signal(123, name="No attribution", _connection=connection)
        db.upsert_signal(123, name="Valid attribution", quelle="mql5", _connection=connection)
    assert db.get_signal(123)["name"] == "Valid attribution"


def test_concurrent_direct_upserts_never_replace_another_source():
    db.init_db()
    start = Barrier(2)

    def write(source):
        start.wait(timeout=10)
        try:
            db.upsert_signal(123, name=source, quelle=source)
            return "saved"
        except ValueError as error:
            assert "ID-Kollision abgewehrt" in str(error)
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ["mql5", "vant"]))
    assert sorted(outcomes) == ["saved", "saved"]
    for source in ("mql5","vant"):
        stored = db.get_signal(123,quelle=source)
        assert stored["name"] == stored["quelle"]
    with pytest.raises(AmbiguousSignalIdentity): db.get_signal(123)


def test_signal_quellen_reads_only_exact_identity_across_both_tables():
    db.init_db()
    db.upsert_signal(123, quelle="mql5")
    db.upsert_signal(999, quelle="unrelated")
    db.katalog_upsert_many("mql5", [{"signal_id": 123}])
    db.katalog_upsert_many("vant", [{"signal_id": 123}])
    db.katalog_upsert_many("pelik", [{"signal_id": 999}])
    before = db.get_signal(123,quelle="mql5")
    assert db.signal_quellen(123) == {"mql5", "vant"}
    assert db.signal_quellen(999) == {"unrelated", "pelik"}
    assert db.signal_quellen(321) == set()
    assert db.get_signal(123,quelle="mql5") == before


@pytest.mark.parametrize("empty", [None, "", " "])
def test_signal_quellen_normalizes_legacy_empty_source(empty,tmp_path,monkeypatch):
    import sqlite3
    source,target=tmp_path/'old.db',tmp_path/'new.db'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE signals(signal_id INTEGER PRIMARY KEY,quelle TEXT)')
        conn.execute('INSERT INTO signals VALUES(123,?)',(empty,))
    identity_migration.migrate_copy(source,target,verify_files=False)
    monkeypatch.setattr(db,'DB_PATH',target)
    assert db.signal_quellen(123)=={'mql5'}


def test_different_source_cannot_inherit_or_overwrite_study_even_with_same_sha():
    db.upsert_signal(123,quelle='mql5')
    db.store_equity_studie(123,'identical-export-sha',{'equity_dd_pct':5},quelle='mql5')
    db.katalog_upsert_many('vant',[{'signal_id':123}])
    with pytest.raises(AmbiguousSignalIdentity): db.get_equity_studie(123)
    assert db.get_equity_studie(123,quelle='vant') is None
    db.store_equity_studie(123,'identical-export-sha',{'equity_dd_pct':9},quelle='vant')
    assert db.get_equity_studie(123,quelle='mql5')['report']['equity_dd_pct']==5
    assert db.get_equity_studie(123,quelle='vant')['report']['equity_dd_pct']==9
    assert 123 not in db.list_equity_studien()
    assert set(db.list_equity_studien(identitaeten=True))=={('mql5',123),('vant',123)}


def test_catalogue_only_conflict_requires_explicit_study_owner():
    db.katalog_upsert_many('pelik',[{'signal_id':123}])
    db.katalog_upsert_many('vant',[{'signal_id':123}])
    with pytest.raises(ValueError,match='explizite Quelle'):
        db.store_equity_studie(123,'sha',{})
    with db._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM equity_studien').fetchone()[0]==0


def test_same_source_in_both_tables_remains_unambiguous_for_studies():
    db.upsert_signal(123,quelle='vant')
    db.katalog_upsert_many('vant',[{'signal_id':123}])
    db.store_equity_studie(123,'sha',{'equity_dd_pct':5},quelle='vant')
    assert db.get_equity_studie(123)['report']['equity_dd_pct']==5
    assert set(db.list_equity_studien())=={123}


def test_study_bulk_filters_unqualified_conflicts_without_per_row_query(monkeypatch):
    for signal_id in range(1,6):
        db.upsert_signal(signal_id,quelle='mql5')
        db.store_equity_studie(signal_id,'sha',{'equity_dd_pct':signal_id},quelle='mql5')
    db.katalog_upsert_many('vant',[{'signal_id':3}])
    queries=[]
    original=db._connect
    @contextmanager
    def traced():
        with original() as conn:
            conn.set_trace_callback(queries.append)
            yield conn
    monkeypatch.setattr(db,'_connect',traced)
    assert set(db.list_equity_studien())=={1,2,4,5}
    assert len([q for q in queries if q.startswith('SELECT')])==2
