"""Minimal worker for the phase-three task lifecycle.

The worker currently validates the queue and lifecycle contract. Real LP and
financial execution will be plugged in behind the same task kinds later.
"""
from __future__ import annotations

import logging
import os

from packages.application.run_registry import RedisStateStore, RunRegistry
from packages.application.task_queue import InMemoryTaskQueue, RedisTaskQueue

LOGGER = logging.getLogger("banboos2.worker")


def build_registry() -> RunRegistry:
    redis_url = os.getenv("BANBOOS2_REDIS_URL")
    return RunRegistry(RedisTaskQueue(redis_url) if redis_url else InMemoryTaskQueue(),
                       RedisStateStore(redis_url) if redis_url else None)


def run_once(registry: RunRegistry) -> bool:
    item = registry.claim_next(timeout=1)
    if item is None:
        return False
    if item.kind == "noop":
        registry.complete(item.run_id, "任务执行完成（noop）")
    else:
        registry.fail(item.run_id, "该任务类型尚未接入执行器", "EXECUTOR_NOT_IMPLEMENTED")
    return True


def main() -> None:
    logging.basicConfig(level=os.getenv("BANBOOS2_LOG_LEVEL", "INFO"))
    registry = build_registry()
    LOGGER.info("Banboos 2.0 worker started")
    while True:
        run_once(registry)


if __name__ == "__main__":
    main()
