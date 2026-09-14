"""Small SQLite runtime for single-host development and manual checks.

It gives the API and Worker a shared durable queue without requiring Redis.
Redis remains the production option; this adapter is intentionally local and
does not replace PostgreSQL as the business database.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from packages.application.task_queue import TaskEnvelope
from packages.contracts.readonly import RunStatus


class SQLiteRuntime:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS runtime_runs ("
                "run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
                "CREATE TABLE IF NOT EXISTS runtime_idempotency ("
                "kind TEXT NOT NULL, idem_key TEXT NOT NULL, run_id TEXT NOT NULL, "
                "PRIMARY KEY(kind, idem_key));"
                "CREATE TABLE IF NOT EXISTS runtime_queue ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, kind TEXT NOT NULL);"
            )

    def save(self, item: RunStatus) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runtime_runs(run_id, payload) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
                (item.run_id, item.model_dump_json()),
            )

    def get(self, run_id: str) -> RunStatus | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM runtime_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return RunStatus.model_validate_json(row[0]) if row else None

    def get_by_key(self, kind: str, key: str) -> RunStatus | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_id FROM runtime_idempotency WHERE kind=? AND idem_key=?",
                (kind, key),
            ).fetchone()
        return self.get(row[0]) if row else None

    def set_key(self, kind: str, key: str, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO runtime_idempotency(kind, idem_key, run_id) VALUES (?, ?, ?)",
                (kind, key, run_id),
            )

    def enqueue(self, task: TaskEnvelope) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runtime_queue(run_id, kind) VALUES (?, ?)",
                (task.run_id, task.kind),
            )

    def claim(self, timeout: int = 1) -> TaskEnvelope | None:
        deadline = time.monotonic() + max(0, timeout)
        while True:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT id, run_id, kind FROM runtime_queue ORDER BY id LIMIT 1"
                ).fetchone()
                if row:
                    connection.execute("DELETE FROM runtime_queue WHERE id=?", (row[0],))
                    return TaskEnvelope(run_id=str(row[1]), kind=str(row[2]))
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection


def runtime_path() -> Path:
    import os

    return Path(os.getenv("BANBOOS2_LOCAL_STATE", "var/runtime/banboos2.sqlite"))
