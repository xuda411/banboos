"""Durable, auditable review state for completed portfolio results."""
from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from packages.contracts.portfolio_review import PortfolioReview

TRANSITIONS = {
    "submit": ("draft", "pending"),
    "approve": ("pending", "approved"),
    "reject": ("pending", "rejected"),
    "archive": ("approved", "archived"),
}


class PortfolioReviewStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or os.getenv("BANBOOS2_REVIEW_DB", "var/portfolio-review.sqlite"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("""CREATE TABLE IF NOT EXISTS portfolio_reviews (
            run_id TEXT PRIMARY KEY, status TEXT NOT NULL, actor TEXT,
            note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS portfolio_review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            action TEXT NOT NULL, from_status TEXT NOT NULL, to_status TEXT NOT NULL,
            actor TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        return db

    def get(self, run_id: str) -> PortfolioReview:
        with self._connect() as db:
            row = db.execute("SELECT status, actor, note, updated_at FROM portfolio_reviews WHERE run_id = ?",
                             (run_id,)).fetchone()
            if row is None:
                return PortfolioReview(run_id=run_id, status="draft")
            events = db.execute("""SELECT action, from_status, to_status, actor, note, created_at
                FROM portfolio_review_events WHERE run_id = ? ORDER BY id""", (run_id,)).fetchall()
        history = [{"action": item[0], "from_status": item[1], "to_status": item[2],
                    "actor": item[3], "note": item[4], "created_at": item[5]} for item in events]
        return PortfolioReview(run_id=run_id, status=row[0], actor=row[1], note=row[2],
                               updated_at=row[3], history=history)

    def transition(self, run_id: str, action: str, actor: str, note: str = "",
                   expected_status: str | None = None) -> PortfolioReview:
        if action not in TRANSITIONS:
            raise ValueError("不支持的审批动作")
        actor = actor.strip()
        if not actor or any(ord(char) < 32 for char in actor):
            raise ValueError("操作者不能为空且不能包含控制字符")
        if len(note) > 1000:
            raise ValueError("审批备注不能超过1000字")
        with self._connect() as db:
            row = db.execute("SELECT status FROM portfolio_reviews WHERE run_id = ?", (run_id,)).fetchone()
            current = row[0] if row else "draft"
            if expected_status and expected_status != current:
                raise ValueError(f"审批状态已变化，当前为{current}")
            from_status, to_status = TRANSITIONS[action]
            if current != from_status:
                raise ValueError(f"当前状态为{current}，不能执行{action}")
            now = datetime.now(UTC).isoformat()
            db.execute("""INSERT INTO portfolio_reviews(run_id, status, actor, note, updated_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,
                actor=excluded.actor, note=excluded.note, updated_at=excluded.updated_at""",
                       (run_id, to_status, actor, note, now))
            db.execute("""INSERT INTO portfolio_review_events(run_id, action, from_status,
                to_status, actor, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                       (run_id, action, from_status, to_status, actor, note, now))
        return self.get(run_id)
