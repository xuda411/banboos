"""Rebuildable local index; immutable snapshot files remain the source of truth."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from packages.infrastructure.dispatch_snapshots import DispatchSnapshots


class PortfolioCatalog:
    def __init__(self):
        self.root = DispatchSnapshots().root

    def register(self, snapshot_id: str, metadata: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.root / "portfolio-index.sqlite")) as db, db:
            self._ensure_schema(db)
            db.execute("INSERT OR IGNORE INTO portfolio_snapshots(snapshot_id, metadata) VALUES (?, ?)",
                       (snapshot_id, json.dumps(metadata, ensure_ascii=False)))

    @staticmethod
    def _ensure_schema(db: sqlite3.Connection) -> None:
        db.execute("""CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            snapshot_id TEXT PRIMARY KEY, metadata TEXT NOT NULL,
            first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )""")

    def rebuild(self) -> int:
        """Rebuild the convenience index from immutable candidate JSON files."""
        self.root.mkdir(parents=True, exist_ok=True)
        index = self.root / "portfolio-index.sqlite"
        count = 0
        # The index is a disposable convenience view. Rebuild it transactionally
        # while immutable content-addressed JSON files remain untouched.
        with closing(sqlite3.connect(index)) as db:
            self._ensure_schema(db)
            db.execute("DELETE FROM portfolio_snapshots")
            for path in sorted(self.root.glob("*.json")):
                snapshot_id = path.stem
                try:
                    # read() verifies the filename digest before indexing; a
                    # partial/corrupt file must never become a history entry.
                    payload = DispatchSnapshots(self.root).read(snapshot_id)
                    if payload.get("kind") != "portfolio-candidates":
                        continue
                    candidates = payload.get("candidates")
                    parameters = payload.get("parameters") or {}
                    if not isinstance(candidates, list) or not isinstance(parameters, dict):
                        continue
                    metadata = {**parameters, "algorithm_version": payload.get("algorithm_version"),
                                "candidate_count": len(candidates)}
                    db.execute("INSERT OR IGNORE INTO portfolio_snapshots(snapshot_id, metadata) VALUES (?, ?)",
                               (snapshot_id, json.dumps(metadata, ensure_ascii=False)))
                    count += 1
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
            db.commit()
        return count

    def page(self, offset: int = 0, limit: int = 20) -> dict:
        index = self.root / "portfolio-index.sqlite"
        if not index.exists():
            self.rebuild()
        with closing(sqlite3.connect(index)) as db:
            self._ensure_schema(db)
            total = db.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0]
            rows = db.execute("""SELECT snapshot_id, metadata, first_seen FROM portfolio_snapshots
                ORDER BY first_seen DESC, snapshot_id ASC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
        return {"total": total, "offset": offset, "limit": limit, "items": [
            {**json.loads(metadata), "snapshot_id": snapshot_id, "saved_at": saved_at}
            for snapshot_id, metadata, saved_at in rows]}
