"""Durable research jobs, isolated from the existing workflow database.

Opening the UI never creates or migrates storage. The first explicit start
creates this feature's own database; existing scanner schemas remain untouched.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else config.DATA_DIR / "abonnenten_analyse" / "jobs.sqlite3"

    @contextlib.contextmanager
    def connection(self, *, create=False):
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30)
        else:
            connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create(self, run: dict) -> None:
        with self.connection(create=True) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    run_id TEXT NOT NULL, signal_ref INTEGER NOT NULL, json TEXT NOT NULL,
                    PRIMARY KEY(run_id,signal_ref));
                CREATE TABLE IF NOT EXISTS calls (
                    run_id TEXT NOT NULL, basis TEXT NOT NULL, status TEXT NOT NULL,
                    reserved INTEGER NOT NULL, tokens INTEGER, response TEXT,
                    meta TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id,basis));
            """)
            connection.execute("INSERT INTO runs VALUES(?,?)", (run["id"], dumps(run)))

    def read(self, run_id: str | None = None) -> dict | None:
        if not self.path.exists():
            return None
        with self.connection() as connection:
            row = connection.execute("SELECT json FROM runs " + ("WHERE id=?" if run_id else "ORDER BY rowid DESC LIMIT 1"),
                                     (run_id,) if run_id else ()).fetchone()
        return json.loads(row[0]) if row else None

    def runs(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connection() as connection:
            rows = connection.execute("SELECT json FROM runs ORDER BY rowid DESC LIMIT 50").fetchall()
        return [json.loads(row[0]) for row in rows]

    def update(self, run_id: str, **changes) -> dict:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT json FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise ValueError("Unbekannter Bewertungslauf")
            run = json.loads(row[0])
            run.update(changes, updated_at=now())
            connection.execute("UPDATE runs SET json=? WHERE id=?", (dumps(run), run_id))
        return run

    def log(self, run_id: str, message: str) -> None:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT json FROM runs WHERE id=?", (run_id,)).fetchone()
            run = json.loads(row[0])
            run["logs"] = [*run.get("logs", []), f"{now()} {message}"][-250:]
            run["detail"] = message
            run["updated_at"] = now()
            connection.execute("UPDATE runs SET json=? WHERE id=?", (dumps(run), run_id))

    def save_task(self, run_id: str, entry: dict) -> None:
        with self.connection() as connection:
            connection.execute("INSERT INTO tasks VALUES(?,?,?) ON CONFLICT(run_id,signal_ref) DO UPDATE SET json=excluded.json",
                               (run_id, int(entry["signal_ref"]), dumps(entry)))

    def tasks(self, run_id: str) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connection() as connection:
            rows = connection.execute("SELECT json FROM tasks WHERE run_id=? ORDER BY signal_ref", (run_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def freeze_source(self, run_id: str, source: str, entries: list[dict], checkpoint: dict) -> dict:
        """Publish membership, popularity reference and checkpoint atomically."""
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = json.loads(connection.execute("SELECT json FROM runs WHERE id=?", (run_id,)).fetchone()[0])
            if run.get("snapshot_quellen", {}).get(source, {}).get("status") == "fertig":
                return run["snapshot_quellen"]
            for row in connection.execute("SELECT signal_ref,json FROM tasks WHERE run_id=?", (run_id,)).fetchall():
                if json.loads(row["json"]).get("quelle") == source:
                    connection.execute("DELETE FROM tasks WHERE run_id=? AND signal_ref=?", (run_id, row["signal_ref"]))
            for entry in entries:
                connection.execute("INSERT INTO tasks(run_id,signal_ref,json) VALUES(?,?,?)",
                                   (run_id, int(entry["signal_ref"]), dumps(entry)))
            checkpoints = dict(run.get("snapshot_quellen") or {})
            checkpoints[source] = checkpoint
            run.update(snapshot_quellen=checkpoints, updated_at=now())
            connection.execute("UPDATE runs SET json=? WHERE id=?", (dumps(run), run_id))
        return checkpoints

    def call(self, run_id: str, basis: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM calls WHERE run_id=? AND basis=?", (run_id, basis)).fetchone()
        return dict(row) if row else None

    def calls(self, run_id: str, prefix: str) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM calls WHERE run_id=? AND basis LIKE ? ORDER BY rowid",
                                      (run_id, prefix + ":%")).fetchall()
        return [dict(row) for row in rows]

    def reserve(self, run_id: str, basis: str, amount: int, limit: int) -> None:
        from .llm.client import LlmBudgetError
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            used = connection.execute("SELECT COALESCE(SUM(CASE WHEN tokens IS NULL THEN reserved ELSE tokens END),0) FROM calls WHERE run_id=?",
                                      (run_id,)).fetchone()[0]
            if used + amount > limit:
                raise LlmBudgetError(f"Laufbudget reicht nicht: {used} verbraucht/reserviert, {amount} nötig, Limit {limit}.")
            connection.execute("INSERT INTO calls(run_id,basis,status,reserved,created_at) VALUES(?,?,'reserved',?,?)",
                               (run_id, basis, amount, now()))

    def finish_call(self, run_id: str, basis: str, *, response: str, tokens: int | None, meta: dict, status="response") -> None:
        with self.connection() as connection:
            connection.execute("UPDATE calls SET status=?,response=?,tokens=?,meta=? WHERE run_id=? AND basis=?",
                               (status, response, tokens, dumps(meta), run_id, basis))

    def spent(self, run_id: str) -> int:
        with self.connection() as connection:
            return int(connection.execute("SELECT COALESCE(SUM(CASE WHEN tokens IS NULL THEN reserved ELSE tokens END),0) FROM calls WHERE run_id=?", (run_id,)).fetchone()[0])
