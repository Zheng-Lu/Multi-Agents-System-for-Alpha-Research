"""SQLite transactions and unique logical keys support replayable, idempotent outcomes."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alpha_mas.models import ExecutionEvent, ModelInvocationRecord, ResearchArtifact, ResearchRun
from alpha_mas.security import redact


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE,
                    run_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_run ON events(run_id, seq);
                CREATE TABLE IF NOT EXISTS artifacts(
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    logical_key TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(run_id, logical_key));
                CREATE TABLE IF NOT EXISTS invocations(
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS configurations(
                    name TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save_run(self, run: ResearchRun) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runs VALUES(?,?) ON CONFLICT(id) "
                "DO UPDATE SET payload=excluded.payload",
                (run.run_id, redact(run.model_dump_json())),
            )

    def run(self, run_id: str) -> ResearchRun:
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return ResearchRun.model_validate_json(row[0])

    def runs(self) -> list[dict]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute("SELECT payload FROM runs ORDER BY rowid DESC")
            ]

    def event(self, event: ExecutionEvent) -> str:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO events(id,run_id,payload) VALUES(?,?,?)",
                (event.event_id, event.run_id, redact(event.model_dump_json())),
            )
        return event.event_id

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        with self.connect() as conn:
            return [
                {"seq": r[0], **json.loads(r[1])}
                for r in conn.execute(
                    "SELECT seq,payload FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                    (run_id, after),
                )
            ]

    def artifact(self, artifact: ResearchArtifact) -> ResearchArtifact:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)",
                (
                    artifact.artifact_id,
                    artifact.run_id,
                    artifact.logical_key,
                    redact(artifact.model_dump_json()),
                ),
            )
            row = conn.execute(
                "SELECT payload FROM artifacts WHERE run_id=? AND logical_key=?",
                (artifact.run_id, artifact.logical_key),
            ).fetchone()
        return ResearchArtifact.model_validate_json(row[0])

    def artifacts(self, run_id: str) -> list[dict]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT payload FROM artifacts WHERE run_id=? ORDER BY rowid", (run_id,)
                )
            ]

    def invocation(self, record: ModelInvocationRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO invocations VALUES(?,?,?)",
                (record.invocation_id, record.run_id, redact(record.model_dump_json())),
            )

    def invocations(self, run_id: str) -> list[dict]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT payload FROM invocations WHERE run_id=? ORDER BY rowid", (run_id,)
                )
            ]

    def configurations(self) -> list[dict]:
        with self.connect() as conn:
            return [
                {"name": r[0], "models": json.loads(r[1])}
                for r in conn.execute("SELECT name,payload FROM configurations ORDER BY name")
            ]

    def save_configuration(self, name: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO configurations VALUES(?,?) ON CONFLICT(name) "
                "DO UPDATE SET payload=excluded.payload",
                (name, redact(json.dumps(payload))),
            )
