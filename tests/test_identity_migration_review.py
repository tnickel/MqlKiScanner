"""Independent migration contracts, using private synthetic databases only."""
from contextlib import closing
import base64
import hashlib
import json
import sqlite3

import pytest

from mqlkiscanner import db, downloader_sync, identity_migration as migration, quellen
from mqlkiscanner.signal_identity import IdentityMigrationRequired


def _legacy(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            CREATE TABLE signals(signal_id INTEGER PRIMARY KEY,name TEXT,platform TEXT,quelle TEXT);
            INSERT INTO signals VALUES(42,'Anchored workflow','MT5','mql5');
            CREATE TABLE agenten_laeufe(id INTEGER PRIMARY KEY,rolle TEXT,quelle TEXT,start TEXT,status TEXT,signal_id INTEGER);
            INSERT INTO agenten_laeufe VALUES(8,'betreuer','daemon','2026-10-18','ok',42);
            CREATE TABLE agenten_schritte(id INTEGER PRIMARY KEY,lauf_id INTEGER,ts TEXT,rolle TEXT,schritt TEXT,status TEXT);
            INSERT INTO agenten_schritte VALUES(9,8,'2026-10-18','betreuer','old step','ok');
        """)
        conn.commit()


def test_current_marker_does_not_authorize_missing_central_identity_unique(tmp_path):
    source, target = tmp_path / "broken-current.db", tmp_path / "candidate.db"
    expected = "externe_id INTEGER NOT NULL,\n    UNIQUE(quellen_uid, externe_id)"
    assert expected in db._SCHEMA
    schema = db._SCHEMA.replace(expected, "externe_id INTEGER NOT NULL", 1)
    with closing(sqlite3.connect(source)) as conn:
        conn.executescript(schema)
        conn.execute("PRAGMA user_version=2")
        conn.execute("INSERT INTO quellen_identitaeten(quellen_uid,kuerzel) VALUES('synthetic-source','mql5')")
        conn.execute("INSERT INTO quellen_alias VALUES('mql5','synthetic-source')")
        conn.execute("INSERT INTO signal_identitaeten(quellen_uid,externe_id) VALUES('synthetic-source',42)")
        conn.execute("INSERT INTO signal_identitaeten(quellen_uid,externe_id) VALUES('synthetic-source',42)")
        conn.commit()
    original = source.read_bytes()
    with pytest.raises(IdentityMigrationRequired):
        migration.migrate_copy(source, target, verify_files=False)
    assert source.read_bytes() == original
    assert not target.exists()


def test_quarantined_non_autoincrement_journal_ids_keep_highwater(tmp_path):
    source, target = tmp_path / "legacy.db", tmp_path / "candidate.db"
    _legacy(source)
    report = migration.migrate_copy(source, target, verify_files=False)
    assert report["tables"]["agenten_laeufe"]["quarantined"] == 1
    assert report["tables"]["agenten_schritte"]["quarantined"] == 1
    with closing(sqlite3.connect(target)) as conn:
        run_id = conn.execute("INSERT INTO agenten_laeufe(rolle,quelle,start,status) "
                              "VALUES('betreuer','gui','2026-10-18','ok')").lastrowid
        step_id = conn.execute("INSERT INTO agenten_schritte(lauf_id,ts,rolle,schritt,status) "
                               "VALUES(?,'2026-10-18','betreuer','new step','ok')", (run_id,)).lastrowid
        conn.commit()
    assert run_id > 8, "Quarantined legacy run IDs must never be reused"
    assert step_id > 9, "Quarantined legacy step IDs must never be reused"


def test_explicit_uid_mirror_can_supply_history_after_primary_transport_archived(monkeypatch):
    primary = db.add_quelle("primary", "Primary", "http://synthetic-primary.invalid")
    owner = db.resolve_identity(42, quelle="primary", create=True)
    mirror = db.add_quelle("mirror", "Explicit mirror", "http://synthetic-mirror.invalid",
                           quellen_uid=owner.quellen_uid)
    db.delete_quelle(primary)
    active = db.list_quellen(nur_aktiv=True)
    assert [(row["id"], row["kuerzel"], row["quellen_uid"]) for row in active] == [
        (mirror, "mirror", owner.quellen_uid)]
    seen = []
    class Client:
        def history(self, signal_id, version):
            seen.append((signal_id, version))
            return [{"timestamp": "2026-10-18T09:00:00", "subscribers": 7}]
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda source: Client())
    assert downloader_sync.sync_history(42, "MT5", quelle="primary") == 1
    assert seen == [(42, "mql5")]
    assert db.get_history(42, quelle="primary")[0]["subscribers"] == 7


def test_catalog_cache_pin_and_reload_keep_explicit_mirror_owner(tmp_path, monkeypatch):
    from mqlkiscanner import fix_signale, ingest, katalog, pipeline
    primary = db.add_quelle("primary", "Primary", "http://synthetic-primary.invalid")
    db.katalog_upsert_many("primary", [{"signal_id": 42, "platform": "MT5", "version": "mql5"}])
    owner = db.resolve_identity(42, quelle="primary")
    mirror = db.add_quelle("mirror", "Explicit mirror", "http://synthetic-mirror.invalid",
                           quellen_uid=owner.quellen_uid)
    fix_signale.setzen(42, quelle="primary")
    db.delete_quelle(primary)
    path = tmp_path / "same-owner.csv"
    path.write_bytes(b"synthetic same-owner trades")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    metrics = tmp_path / "same-owner-metrics.json"
    metrics.write_text(json.dumps({"signalId": 42, "version": "mql5", "metrics": {
        "Currency": "USD", "InitialDeposit": 1000}}), encoding="utf-8")
    db.store_quellen_artefakt(mirror, 42, "mql5", "trades", sha, str(path))
    db.store_quellen_artefakt(mirror, 42, "mql5", "metrics",
                             hashlib.sha256(metrics.read_bytes()).hexdigest(), str(metrics))
    rows, stats = katalog.katalog_resultate(gescannt=set(), studien={})
    assert [(r.quelle, r.id, r.quelle_id, r.trades_path) for r in rows] == [("primary", 42, mirror, str(path))]
    assert stats[("primary", 42)]["initial_deposit_usd"] == 1000
    assert fix_signale.fix_keys({}) == {("primary", 42)}
    workflow = pipeline.ScanResult(id=42, quelle="primary", platform="MT5", quelle_id=primary,
        quelle_version="mql5", signal_ref=owner.signal_ref, quellen_uid=owner.quellen_uid,
        trades_path=str(path), trades_sha256=sha)
    assert katalog.quellen_referenz(workflow) == (mirror, "mql5")
    assert katalog.metrics_stats(workflow)["initial_deposit_usd"] == 1000
    assert katalog.workflow_stats_bulk([workflow], {})[("primary", 42)]["initial_deposit_usd"] == 1000
    calls = []
    monkeypatch.setattr(ingest, "hole_metrics", lambda q, *a, **k: calls.append(q["id"]) or {
        "signalId": 42, "version": "mql5", "metrics": {"Currency": "USD"}})
    monkeypatch.setattr(ingest, "hole_trades", lambda q, *a, **k: calls.append(q["id"]) or (str(path), False))
    assert katalog.lade_signal_daten(workflow) == (str(path), False)
    assert calls == [mirror, mirror]
    db.update_quelle(mirror, kuerzel="renamed-mirror")
    rows, stats = katalog.katalog_resultate(gescannt=set(), studien={})
    assert rows[0].quelle == "renamed-mirror" and rows[0].signal_ref == owner.signal_ref
    assert stats[("renamed-mirror", 42)]["initial_deposit_usd"] == 1000
    assert fix_signale.fix_keys({}) == {("renamed-mirror", 42)}
    catalog_calls = []
    monkeypatch.setattr(ingest, "hole_katalog", lambda q, **kwargs:
        catalog_calls.append((q["id"], kwargs["min_subscribers"])) or [
            {"signalId": 42, "version": "mql5"}])
    summary = katalog.sync(kuerzel="primary")
    assert catalog_calls == [(mirror, 0)]
    assert summary["gesamt"] == 1
    assert summary["quellen"]["renamed-mirror"]["gelaufen_am"] is not None


def test_active_and_quarantine_preserve_all_rows_blobs_and_file_references(tmp_path):
    source, target = tmp_path / "legacy.db", tmp_path / "candidate.db"
    _legacy(source)
    trades = tmp_path / "original.csv"
    trades.write_bytes(b"synthetic immutable trade evidence")
    digest = hashlib.sha256(trades.read_bytes()).hexdigest()
    blob = b"\x00\xff\x81 original blob"
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("CREATE TABLE trade_files(signal_id INTEGER PRIMARY KEY,path TEXT,sha256 TEXT)")
        conn.execute("INSERT INTO trade_files VALUES(42,?,?)", (str(trades), digest))
        conn.execute("CREATE TABLE unknown_signal_notes(signal_id INTEGER,payload BLOB)")
        conn.execute("INSERT INTO unknown_signal_notes VALUES(42,?)", (blob,))
        conn.execute("CREATE TABLE global_blob(id INTEGER PRIMARY KEY,payload BLOB)")
        conn.execute("INSERT INTO global_blob VALUES(8,?)", (blob,))
        conn.commit()
    original_db, original_trades = source.read_bytes(), trades.read_bytes()
    report = migration.migrate_copy(source, target)
    assert all(item["before"] == item["migrated"] + item["quarantined"]
               for item in report["tables"].values())
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT path,sha256 FROM trade_files").fetchone() == (str(trades), digest)
        assert conn.execute("SELECT payload FROM global_blob").fetchone()[0] == blob
        payload = json.loads(conn.execute("SELECT datensatz_json FROM migration_quarantaene "
            "WHERE ursprung_tabelle='unknown_signal_notes'").fetchone()[0])
        assert payload["signal_id"] == 42
        assert base64.b64decode(payload["payload"]["__sqlite_blob_base64__"]) == blob
    assert report["files"]["unchanged_references"] and report["files"]["verified"] == 1
    assert source.read_bytes() == original_db and trades.read_bytes() == original_trades
