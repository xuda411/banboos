"""Small in-memory run registry for the first API contract milestone.

The registry deliberately does not execute investment or control work yet. It
gives the web client a stable asynchronous job contract that can later be
backed by Redis/Celery without changing the HTTP shape.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from itertools import batched
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
    def status_counts(self) -> dict[str, int]: ...
    def list(self, kind: str | None = None, status: str | None = None,
             limit: int = 50) -> list[RunStatus]: ...


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

    def status_counts(self) -> dict[str, int]:
        return dict(Counter(item.status for item in self._items.values()))

    def list(self, kind: str | None = None, status: str | None = None,
             limit: int = 50) -> list[RunStatus]:
        items = list(self._items.values())
        return [item for item in reversed(items)
                if (kind is None or item.kind == kind) and (status is None or item.status == status)][:limit]


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

    def status_counts(self) -> dict[str, int]:
        # Existing Redis installations need no new index or payload migration.
        # SCAN may repeat keys; count each run once and bound each MGET request.
        counts: Counter[str] = Counter()
        seen: set[str] = set()
        for batch in batched(self._client.scan_iter(match="banboos2:run:*", count=128), 128):
            keys = []
            for key in batch:
                if key not in seen:
                    keys.append(key)
                    seen.add(key)
            if not keys:
                continue
            for payload in self._client.mget(keys):
                if payload is not None:
                    status = json.loads(payload)["status"]
                    if not isinstance(status, str) or not status:
                        raise ValueError("invalid stored run status")
                    counts[status] += 1
        return dict(counts)

    def list(self, kind: str | None = None, status: str | None = None,
             limit: int = 50) -> list[RunStatus]:
        items: list[RunStatus] = []
        for key in self._client.scan_iter(match="banboos2:run:*"):
            payload = self._client.get(key)
            if not payload:
                continue
            item = RunStatus.model_validate_json(payload)
            if (kind is None or item.kind == kind) and (status is None or item.status == status):
                items.append(item)
        return sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]


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

    def status_counts(self) -> dict[str, int]:
        with self._lock:
            counts = dict.fromkeys(("queued", "running", "succeeded", "failed", "cancelled"), 0)
            counts.update(self._store.status_counts())
            return counts

    def list(self, kind: str | None = None, status: str | None = None,
             limit: int = 50) -> list[RunStatus]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._lock:
            return self._store.list(kind, status, limit)

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

    def recover_running(self) -> int:
        """Requeue tasks left in ``running`` state after a worker restart."""
        recovered = 0
        with self._lock:
            running = self._store.list(status="running", limit=500)
            for item in running:
                updated = item.model_copy(update={
                    "status": "queued", "progress": 0,
                    "message": "检测到执行器重启，任务已重新排队",
                    "error_code": None,
                })
                self._store.save(updated)
                self._queue.enqueue(TaskEnvelope(run_id=item.run_id, kind=item.kind))
                recovered += 1
        return recovered

    def complete(self, run_id: str, message: str = "任务完成",
                 result: dict | None = None) -> RunStatus | None:
        return self._transition(run_id, "succeeded", 100, message, result=result)

    def update_progress(self, run_id: str, progress: int, message: str) -> RunStatus | None:
        with self._lock:
            item = self._store.get(run_id)
            if item is None or item.status != "running":
                return item
            updated = item.model_copy(update={"progress": max(0, min(99, progress)), "message": message})
            self._store.save(updated)
            return updated

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
            if item is None or item.status != "running":
                return None
            updated = item.model_copy(update={"status": status, "progress": progress,
                                              "message": message, "error_code": error_code,
                                              "result": result, "completed_at": datetime.now(UTC)})
            self._store.save(updated)
            return updated
