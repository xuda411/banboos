"""Task queue ports and local/Redis implementations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Protocol

import redis


@dataclass(frozen=True)
class TaskEnvelope:
    run_id: str
    kind: str


class TaskQueue(Protocol):
    def enqueue(self, task: TaskEnvelope) -> None: ...
    def claim(self, timeout: int = 1) -> TaskEnvelope | None: ...


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._queue: Queue[TaskEnvelope] = Queue()

    def enqueue(self, task: TaskEnvelope) -> None:
        self._queue.put(task)

    def claim(self, timeout: int = 1) -> TaskEnvelope | None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None


class RedisTaskQueue:
    queue_name = "banboos2:analysis:queue"

    def __init__(self, url: str) -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def enqueue(self, task: TaskEnvelope) -> None:
        self._client.rpush(self.queue_name, json.dumps({"run_id": task.run_id, "kind": task.kind}))

    def claim(self, timeout: int = 1) -> TaskEnvelope | None:
        item = self._client.blpop(self.queue_name, timeout=timeout)
        if not item:
            return None
        payload = json.loads(item[1])
        return TaskEnvelope(run_id=str(payload["run_id"]), kind=str(payload["kind"]))
