"""Compose read-only runtime counters without mixing them with device health."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from redis.exceptions import RedisError

from packages.contracts.operations import EdgeCounts, OperationsSummary, TaskCounts


class NodeSource(Protocol):
    @property
    def data_mode(self) -> str: ...
    def node_count(self) -> int: ...


class TaskSource(Protocol):
    def status_counts(self) -> dict[str, int]: ...


class EdgeSource(Protocol):
    def operations_counts(self) -> EdgeCounts: ...


class OperationsUnavailable(RuntimeError):
    def __init__(self, component: str):
        super().__init__("operations summary temporarily unavailable")
        self.component = component


def _read[T](component: str, reader: Callable[[], T]) -> T:
    try:
        return reader()
    except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, RedisError) as error:
        raise OperationsUnavailable(component) from error


class OperationsService:
    def __init__(self, nodes: NodeSource, tasks: TaskSource, edge: EdgeSource):
        self.nodes = nodes
        self.tasks = tasks
        self.edge = edge

    def summary(self) -> OperationsSummary:
        started = datetime.now(UTC)
        count, mode = _read("nodes", lambda: (self.nodes.node_count(), self.nodes.data_mode))
        tasks = _read("tasks", lambda: TaskCounts(by_status=self.tasks.status_counts()))
        edge = _read("telemetry", self.edge.operations_counts)
        return OperationsSummary(
            collection_started_at=started, generated_at=datetime.now(UTC),
            node_count=count, data_mode=mode, task_counts=tasks,
            telemetry=edge.telemetry, alerts=edge.alerts,
        )
