"""Small in-memory run registry for the first API contract milestone.

The registry deliberately does not execute investment or control work yet. It
gives the web client a stable asynchronous job contract that can later be
backed by Redis/Celery without changing the HTTP shape.
"""
from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

import redis

from packages.application.task_queue import InMemoryTaskQueue, TaskEnvelope, TaskQueue
from packages.contracts.readonly import RunStatus


class StateStore(Protocol):
    def save(self, item: RunStatus) -> None: ...
    def get(self, run_id: str) -> RunStatus | None: ...
    def get_by_key(self, kind: str, key: str) -> RunStatus | None: ...
    def set_key(self, kind: str, key: str, run_id: str) -> None: ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._items: dict[str, RunStatus] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def save(self, item: RunStatus) -> None:
        self._items[item.run_id] = item

    def get(self, run_id: str) -> RunStatus | None:
        return self._items.get(run_id)

    def get_by_key(self, kind: str, key: str) -> RunStatus | None:
        run_id = self._idempotency.get((kind, key))
        return self._items.get(run_id) if run_id else None

    def set_key(self, kind: str, key: str, run_id: str) -> None:
        self._idempotency[(kind, key)] = run_id


class RedisStateStore:
    def __init__(self, url: str) -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def save(self, item: RunStatus) -> None:
        self._client.set(f"banboos2:run:{item.run_id}", item.model_dump_json())

    def get(self, run_id: str) -> RunStatus | None:
        payload = self._client.get(f"banboos2:run:{run_id}")
        return RunStatus.model_validate_json(payload) if payload else None

    def get_by_key(self, kind: str, key: str) -> RunStatus | None:
        run_id = self._client.get(f"banboos2:idempotency:{kind}:{key}")
        return self.get(run_id) if run_id else None

    def set_key(self, kind: str, key: str, run_id: str) -> None:
        self._client.set(f"banboos2:idempotency:{kind}:{key}", run_id)


class RunRegistry:
    def __init__(self, queue: TaskQueue | None = None, store: StateStore | None = None) -> None:
        self._store = store or InMemoryStateStore()
        self._lock = Lock()
        self._queue = queue or InMemoryTaskQueue()

    def submit(self, kind: str, idempotency_key: str | None = None,
               parameters: dict | None = None) -> RunStatus:
        with self._lock:
            if idempotency_key:
                existing = self._store.get_by_key(kind, idempotency_key)
                if existing:
                    return existing
            now = datetime.now(UTC)
            item = RunStatus(run_id=str(uuid4()), kind=kind, status="queued", created_at=now,
                             message="已进入任务队列", parameters=parameters or {})
            self._store.save(item)
            if idempotency_key:
                self._store.set_key(kind, idempotency_key, item.run_id)
            self._queue.enqueue(TaskEnvelope(run_id=item.run_id, kind=item.kind))
            return item

    def get(self, run_id: str) -> RunStatus | None:
        with self._lock:
            return self._store.get(run_id)

    def claim_next(self, timeout: int = 1) -> RunStatus | None:
        task = self._queue.claim(timeout)
        if task is None:
            return None
        with self._lock:
            item = self._store.get(task.run_id)
            if item is None or item.status != "queued":
                return None
            updated = item.model_copy(update={"status": "running", "progress": 5,
                                              "message": "执行器已领取任务"})
            self._store.save(updated)
            return updated

    def complete(self, run_id: str, message: str = "任务完成",
                 result: dict | None = None) -> RunStatus | None:
        return self._transition(run_id, "succeeded", 100, message, result=result)

    def fail(self, run_id: str, message: str, error_code: str = "TASK_FAILED") -> RunStatus | None:
        return self._transition(run_id, "failed", 100, message, error_code)

    def cancel(self, run_id: str) -> RunStatus | None:
        with self._lock:
            item = self._store.get(run_id)
            if item is None or item.status not in {"queued", "running"}:
                return item
            updated = item.model_copy(update={"status": "cancelled", "progress": item.progress,
                                              "message": "任务已取消", "completed_at": datetime.now(UTC)})
            self._store.save(updated)
            return updated

    def _transition(self, run_id: str, status: str, progress: int, message: str,
                    error_code: str | None = None, result: dict | None = None) -> RunStatus | None:
        with self._lock:
            item = self._store.get(run_id)
            if item is None:
                return None
            updated = item.model_copy(update={"status": status, "progress": progress,
                                              "message": message, "error_code": error_code,
                                              "result": result, "completed_at": datetime.now(UTC)})
            self._store.save(updated)
            return updated
