"""Explicit, versioned COPY migration. This module never activates a database.

Only the destination is written. The SQLite backup API includes committed WAL
pages in a consistent private snapshot. Ambiguous/unowned rows remain losslessly
available in migration_quarantaene inside the private candidate database.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from . import db
from .signal_identity import IdentityError, source_label


MIGRATION_VERSION = 1


@contextmanager
def _connection(*args,**kwargs):
    conn=sqlite3.connect(*args,**kwargs)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _json(value):
    # Blob cells are preserved as base64; normal text/JSON is never rewritten.
    return json.dumps(value, ensure_ascii=False, default=lambda obj:
        {"__sqlite_blob_base64__": base64.b64encode(obj).decode("ascii")})


def backup_database(source_path, backup_path):
    """Create a consistent, exclusive destination snapshot, without source writes."""
    source, target = Path(source_path).resolve(), Path(backup_path).resolve()
    if source == target or target.exists():
        raise ValueError("Backupziel muss neu und vom Quellpfad verschieden sein")
    source_sha_before = _hash(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation also prevents an accidental overwrite after validation.
    with target.open("xb"):
        pass
    try:
        with _connection(source.as_uri() + "?mode=ro", uri=True) as original:
            with _connection(target) as snapshot:
                original.backup(snapshot)
        source_sha_after = _hash(source)
        return {"path": str(target), "sha256": _hash(target), "size_bytes": target.stat().st_size,
                "source_file_sha256_before":source_sha_before,
                "source_file_sha256_after":source_sha_after,
                "source_file_unchanged_during_backup":source_sha_before==source_sha_after}
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def migrate_copy(source_path, destination_path, *, verify_files=True, settings=None):
    """Build and validate a new candidate; never rename it onto the live DB.

    settings may supply legacy fix_signal_ids; only unambiguous registered owners
    can inherit these unqualified pins. Unresolved values remain in quarantine.
    Report contains counts/hashes only, never row payloads or credentials.
    A retained *.legacy-backup.sqlite is the unmodified rollback snapshot.
    """
    source, destination = Path(source_path).resolve(), Path(destination_path).resolve()
    if source == destination or destination.exists():
        raise ValueError("Migrationsziel muss neu und vom Quellpfad verschieden sein")
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(destination.name + ".legacy-backup.sqlite")
    backup_info = backup_database(source, backup)
    handle, staged_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".staged", dir=destination.parent)
    os.close(handle)
    staged = Path(staged_name)
    report = {"migration_version": MIGRATION_VERSION, "schema_version": db.SCHEMA_VERSION,
              "backup": backup_info, "tables": {}, "files": {}, "activated": False}
    try:
        with _connection(backup.as_uri()+"?mode=ro", uri=True) as old:
            old.row_factory = sqlite3.Row
            schema = {row["name"]: row["sql"] for row in old.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            version = old.execute("PRAGMA user_version").fetchone()[0]
            if "signal_identitaeten" in schema:
                if version != db.SCHEMA_VERSION:
                    raise ValueError(f"Nicht unterstuetzte Identitaetsversion {version}")
                with _connection(staged) as new:
                    old.backup(new)
                report["already_current"] = True
                for table in schema:
                    count = old.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]
                    report["tables"][table] = {"before": count, "migrated": count, "quarantined": 0}
            else:
                with _connection(staged) as new:
                    new.row_factory = sqlite3.Row
                    new.execute("PRAGMA foreign_keys=ON")
                    _migrate_legacy(old, new, schema, report, settings or {})
                    new.execute(f"PRAGMA user_version={db.SCHEMA_VERSION}")
            with _connection(staged) as new:
                new.row_factory = sqlite3.Row
                db._check_schema(new)
                report["integrity_check"] = new.execute("PRAGMA integrity_check").fetchone()[0]
                report["foreign_key_errors"] = len(new.execute("PRAGMA foreign_key_check").fetchall())
                report["identity_count"] = new.execute("SELECT COUNT(*) FROM signal_identitaeten").fetchone()[0]
                report["source_count"] = new.execute("SELECT COUNT(*) FROM quellen_identitaeten").fetchone()[0]
                report["files"] = _file_check(old, new, verify_files)
                if report["integrity_check"] != "ok" or report["foreign_key_errors"]:
                    raise ValueError("Migration verletzt SQLite-Integritaet oder Fremdschluessel")
                if not all(item["before"] == item["migrated"] + item["quarantined"]
                           for item in report["tables"].values()):
                    raise ValueError("Migrations-Mengenbilanz verletzt")
                new.execute("PRAGMA journal_mode=DELETE")
        if _hash(backup) != backup_info["sha256"]:
            raise ValueError("Originalbackup hat sich waehrend der Migration veraendert")
        # Exclusive publication, with no activation and no clobber of an existing target.
        os.link(staged, destination)
        staged.unlink()
        report["destination"] = str(destination)
        report["destination_sha256"] = _hash(destination)
        return report
    finally:
        staged.unlink(missing_ok=True)


def _migrate_legacy(old, new, schema, report, settings):
    from .agenten import dossier, journal
    new.executescript(db._SCHEMA)
    new.executescript(journal._SCHEMA)
    new.executescript(dossier._SCHEMA)
    new.executescript("""
        CREATE TABLE migration_protokoll (
            migration_version INTEGER NOT NULL, schema_version INTEGER NOT NULL,
            backup_sha256 TEXT NOT NULL, angelegt_am TEXT NOT NULL);
    """)
    new.execute("INSERT INTO migration_protokoll VALUES(?,?,?,?)",
                (MIGRATION_VERSION, db.SCHEMA_VERSION, report["backup"]["sha256"],db._now()))
    rows = {table: [dict(row) for row in old.execute(f"SELECT * FROM {_quote(table)}")]
            for table in schema}
    budget_before = _budget_snapshot(old)
    # Register explicit source ownership from all anchored tables, including catalog-only.
    workflow = {}
    for row in rows.get("signals", []):
        identity = db.resolve_identity(row["signal_id"], quelle=source_label(row.get("quelle")),
                                       create=True, _connection=new)
        workflow[int(row["signal_id"])] = identity
    for row in rows.get("katalog_signale", []):
        db.resolve_identity(row["signal_id"],quelle=source_label(row.get("quelle")),create=True,_connection=new)
    connections = {}
    for row in rows.get("datenquellen", []):
        source = db._source(new,source_label(row.get("kuerzel")),create=True)
        connections[row["id"]] = source
    for row in rows.get("quellen_artefakte", []):
        source = connections.get(row["quelle_id"])
        if source:
            db.resolve_identity(row["signal_id"],quelle=source["kuerzel"],create=True,_connection=new)
    # Never interpret scan type (full/partial) or trigger (gui/daemon) as owner.
    workflow_children = {"trade_files", "forensik", "analyses"}
    stats = report["tables"]
    for table, items in rows.items():
        stats[table] = {"before":len(items),"migrated":0,"quarantined":0}
        if table not in {r[0] for r in new.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            if "signal_id" in {r[1] for r in old.execute(f"PRAGMA table_info({_quote(table)})")}:
                # Unknown signal-bearing extensions cannot safely reuse ID-only schema.
                continue
            new.execute(schema[table])
    # Known dependencies must be copied parent-first; other tables are global.
    order = ["datenquellen", "signals", "katalog_signale", "agenten_laeufe", "agenten_schritte",
             "trade_deltas", "dossier_profil", "dossier_beobachtungen"]
    order += [table for table in schema if table not in order]
    quarantined_runs, quarantined_steps, quarantined_deltas = set(),set(),set()

    def quarantine(table, row, reason):
        cursor=new.execute("INSERT INTO migration_quarantaene(ursprung_tabelle,grund,datensatz_json) VALUES(?,?,?)",
                    (table,reason,_json(row)))
        stats[table]["quarantined"] += 1
        if table=="agenten_laeufe": quarantined_runs.add(row["id"])
        if table=="agenten_schritte":
            quarantined_steps.add(row["id"])
            # Accounting provenance is known even when signal ownership is not.
            # This receipt is not an active journal step and contains no prompt.
            new.execute("INSERT INTO agenten_budget_altkosten(schritt_id,quarantaene_id,ts,tokens,budget_ledger,prompt_vorhanden) "
                        "VALUES(?,?,?,?,?,?)",(row["id"],cursor.lastrowid,row.get("ts"),row.get("tokens"),
                        row.get("budget_ledger",0),int(row.get("prompt") is not None)))
        if table=="trade_deltas": quarantined_deltas.add(row["id"])

    for table in order:
        for original in rows.get(table, []):
            row = dict(original)
            try:
                if table=="datenquellen":
                    source = connections[row["id"]]
                    row["kuerzel"] = source["kuerzel"]
                    row["quellen_uid"] = source["quellen_uid"]
                    row["archiviert"] = 0
                if table=="agenten_schritte" and row.get("lauf_id") in quarantined_runs:
                    raise IdentityError("Journal-Lauf ist nicht eindeutig zuordenbar")
                if table=="dossier_beobachtungen" and (row.get("delta_ref") in quarantined_deltas
                        or row.get("schritt_ref") in quarantined_steps):
                    raise IdentityError("Dossier-Verweis liegt in Quarantaene")
                if "signal_id" in row:
                    external = row.pop("signal_id")
                    if table=="analyses" and external in (None,0) and row.get("kind") in ("portfolio","portfolio_ungueltig"):
                        identity = None
                    elif table=="agenten_laeufe" and external is None:
                        identity = None
                    elif table in ("signals","katalog_signale"):
                        identity = db.resolve_identity(external,quelle=source_label(row.get("quelle")),_connection=new)
                        row["quelle"] = identity.quelle
                        db._guard_platform(new,identity.signal_ref,row.get("platform"),row.get("version"))
                    elif table=="quellen_artefakte":
                        source = connections.get(row["quelle_id"])
                        if not source: raise IdentityError("Artefakt-Verbindung fehlt")
                        identity = db.resolve_identity(external,quelle=source["kuerzel"],_connection=new)
                    elif table in workflow_children:
                        identity = workflow.get(int(external)) if external is not None else None
                        if identity is None: raise IdentityError("Workflow-Elternsignal fehlt")
                    else:
                        # A CURRENT single catalog/workflow owner does not prove
                        # who produced an older ID-only child. Even equal SHA or
                        # platform is not historical source provenance.
                        historical_source = row.pop("signal_quelle", None) or row.pop("datenquelle", None)
                        if not historical_source:
                            raise IdentityError("Historischer Quellenbeleg fehlt; aktueller Registertreffer reicht nicht")
                        identity = db.resolve_identity(external,quelle=historical_source,_connection=new)
                        if identity is None: raise IdentityError("Historischer Quellenbeleg besitzt keine registrierte Identitaet")
                    row["signal_ref"] = identity.signal_ref if identity else None
                    if table=="dossier_beobachtungen":
                        dossier._validate_observation_links(new,row["signal_ref"],row.get("delta_ref"),row.get("schritt_ref"))
                target_columns = {r[1] for r in new.execute(f"PRAGMA table_info({_quote(table)})")}
                if not target_columns:
                    raise IdentityError("Unbekannte signalbezogene Erweiterung braucht expliziten Migrationsadapter")
                if not set(row) <= target_columns:
                    raise IdentityError("Nicht abbildbare Altspalten: " + ','.join(sorted(set(row)-target_columns)))
                # Preserve all original columns and record IDs; never INSERT OR IGNORE.
                columns = list(row)
                new.execute(f"INSERT INTO {_quote(table)} ({','.join(_quote(c) for c in columns)}) "
                            f"VALUES ({','.join('?' for _ in columns)})", [row[c] for c in columns])
                stats[table]["migrated"] += 1
            except (IdentityError,sqlite3.IntegrityError) as error:
                quarantine(table,original,str(error))
    report["legacy_pins"] = {"before":0,"migrated":0,"quarantined":0}
    for external in settings.get("fix_signal_ids",[]):
        report["legacy_pins"]["before"] += 1
        try:
            identity = db.resolve_identity(int(external),_connection=new)
            if identity is None: raise IdentityError("Legacy-Fix ohne belegten Eigentuemer")
            new.execute("INSERT INTO signal_fixierungen(signal_ref,updated_at) VALUES(?,?) "
                        "ON CONFLICT(signal_ref) DO NOTHING",(identity.signal_ref,db._now()))
            report["legacy_pins"]["migrated"] += 1
        except (IdentityError,ValueError,TypeError) as error:
            new.execute("INSERT INTO migration_quarantaene(ursprung_tabelle,grund,datensatz_json) VALUES(?,?,?)",
                        ("config.fix_signal_ids",str(error),_json({"signal_id":external})))
            report["legacy_pins"]["quarantined"] += 1
    # Unknown views/triggers are deliberately not executable in the new DB.
    # Known original indexes on untouched global tables remain safe and useful.
    for row in old.execute("SELECT name,sql,tbl_name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
        if row["tbl_name"] not in schema or "signal_id" in row["sql"]:
            continue
        new.execute(re.sub(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+",r"CREATE \1INDEX IF NOT EXISTS ",row["sql"],flags=re.I))
    # Quarantine must not make historical audit IDs reusable by a later insert.
    report["sequence_highwatermarks_preserved"] = True
    old_sequences = dict(old.execute("SELECT name,seq FROM sqlite_sequence")) if old.execute(
        "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone() else {}
    for name, in new.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%AUTOINCREMENT%'"):
        if name in schema and "id" in {r[1] for r in old.execute(f"PRAGMA table_info({_quote(name)})")}:
            seq=max(old_sequences.get(name,0),old.execute(f"SELECT COALESCE(MAX(id),0) FROM {_quote(name)}").fetchone()[0])
            previous = new.execute("SELECT seq FROM sqlite_sequence WHERE name=?",(name,)).fetchone()
            if previous:
                new.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name=?",(seq,name))
            else:
                new.execute("INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)",(name,seq))
    budget_after = _budget_snapshot(new)
    if budget_before != budget_after:
        raise ValueError("Agenten-Budgetverbrauch wurde durch Migration veraendert")
    report["budget_preservation"] = {"unchanged":True,"before":budget_before,"after":budget_after,
        "cost_receipts":new.execute("SELECT COUNT(*) FROM agenten_budget_altkosten").fetchone()[0]}


def _budget_snapshot(conn):
    """Compare paid and reserved accounting by all known day/month prefixes."""
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    periods=set()
    selects=[]
    if "agenten_schritte" in tables:
        columns={r[1] for r in conn.execute("PRAGMA table_info(agenten_schritte)")}
        flag="budget_ledger=0" if "budget_ledger" in columns else "1=1"
        if {"ts","tokens","prompt"} <= columns:
            selects.append(f"SELECT ts,tokens FROM agenten_schritte WHERE prompt IS NOT NULL AND {flag}")
    if "agenten_budget_altkosten" in tables:
        selects.append("SELECT ts,tokens FROM agenten_budget_altkosten WHERE prompt_vorhanden=1 AND budget_ledger=0")
    for query in selects:
        for row in conn.execute(query):
            if row[0] is not None:
                periods.update((str(row[0])[:10],str(row[0])[:7]))
    if "agenten_budget_versuche" in tables:
        for day,month in conn.execute("SELECT tag,monat FROM agenten_budget_versuche"):
            periods.update((day,month))
    result={}
    for period in sorted(periods):
        legacy=sum(conn.execute("SELECT COALESCE(SUM(tokens),0) FROM ("+query+") WHERE ts LIKE ?",
                                (period+'%',)).fetchone()[0] for query in selects)
        paid=reserved=0
        if "agenten_budget_versuche" in tables:
            column="tag" if len(period)==10 else "monat"
            paid,reserved=conn.execute("SELECT COALESCE(SUM(CASE WHEN abgeschlossen=1 THEN tokens ELSE 0 END),0),"
                "COALESCE(SUM(CASE WHEN abgeschlossen=1 THEN tokens ELSE reserviert END),0) FROM agenten_budget_versuche "
                f"WHERE {column}=?",(period,)).fetchone()
        result[period]={"spent":int(legacy+paid),"used_or_reserved":int(legacy+reserved)}
    return result


def _file_check(old,new,verify):
    report = {"verified":0,"missing":0,"sha_mismatch":0,"unchanged_references":True,
              "verification_requested":bool(verify)}
    for table in ("trade_files","quellen_artefakte"):
        present = {row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in present:
            continue
        original = {(row[0],row[1]) for row in old.execute(f"SELECT path,sha256 FROM {table}")}
        current = {(row[0],row[1]) for row in new.execute(f"SELECT path,sha256 FROM {table}")}
        if not current <= original:
            report["unchanged_references"] = False
        if verify:
            for path,expected in original:
                if not path or not Path(path).is_file(): report["missing"] += 1
                elif not expected or _hash(path) != expected: report["sha_mismatch"] += 1
                else: report["verified"] += 1
    return report
