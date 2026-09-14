"""Small in-memory run registry for the first API contract milestone.

The registry deliberately does not execute investment or control work yet. It
gives the web client a stable asynchronous job contract that can later be
backed by Redis/Celery without changing the HTTP shape.
"""
from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from packages.contracts.readonly import RunStatus


class RunRegistry:
    def __init__(self) -> None:
        self._items: dict[str, RunStatus] = {}
        self._idempotency: dict[tuple[str, str], str] = {}
        self._lock = Lock()

    def submit(self, kind: str, idempotency_key: str | None = None) -> RunStatus:
        with self._lock:
            if idempotency_key:
                existing_id = self._idempotency.get((kind, idempotency_key))
                if existing_id:
                    return self._items[existing_id]
            now = datetime.now(UTC)
            item = RunStatus(run_id=str(uuid4()), kind=kind, status="queued", created_at=now,
                             message="已进入任务队列，执行器将在后续阶段接入")
            self._items[item.run_id] = item
            if idempotency_key:
                self._idempotency[(kind, idempotency_key)] = item.run_id
            return item

    def get(self, run_id: str) -> RunStatus | None:
        with self._lock:
            return self._items.get(run_id)
