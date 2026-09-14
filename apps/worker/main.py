"""Minimal worker for the phase-three task lifecycle.

The worker currently validates the queue and lifecycle contract. Real LP and
financial execution will be plugged in behind the same task kinds later.
"""
from __future__ import annotations

import logging
import os
from datetime import date

from packages.application.readonly_service import ReadonlyService
from packages.application.run_registry import RedisStateStore, RunRegistry
from packages.application.task_queue import InMemoryTaskQueue, RedisTaskQueue

LOGGER = logging.getLogger("banboos2.worker")


def build_registry() -> RunRegistry:
    redis_url = os.getenv("BANBOOS2_REDIS_URL")
    return RunRegistry(RedisTaskQueue(redis_url) if redis_url else InMemoryTaskQueue(),
                       RedisStateStore(redis_url) if redis_url else None)


def run_once(registry: RunRegistry, readonly_service: ReadonlyService | None = None) -> bool:
    item = registry.claim_next(timeout=1)
    if item is None:
        return False
    if item.kind == "noop":
        registry.complete(item.run_id, "任务执行完成（noop）")
    elif item.kind == "price-summary":
        try:
            parameters = item.parameters
            service = readonly_service or ReadonlyService()
            result = service.price(
                int(parameters["node_id"]), str(parameters["market"]),
                date.fromisoformat(str(parameters["start_date"])),
                date.fromisoformat(str(parameters["end_date"])),
            ).model_dump(mode="json")
            registry.complete(item.run_id, "节点电价摘要计算完成", result)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"节点电价摘要计算失败：{error}", "PRICE_SUMMARY_FAILED")
    elif item.kind == "price-analysis":
        try:
            parameters = item.parameters
            service = readonly_service or ReadonlyService()
            result = service.analyze_price(
                int(parameters["node_id"]), str(parameters["market"]),
                date.fromisoformat(str(parameters["start_date"])),
                date.fromisoformat(str(parameters["end_date"])), float(parameters["power_mw"]),
                float(parameters["capacity_mwh"]), float(parameters.get("round_trip_efficiency", 0.92)),
            ).model_dump(mode="json")
            registry.complete(item.run_id, "节点价差分析完成", result)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"节点价差分析失败：{error}", "PRICE_ANALYSIS_FAILED")
    else:
        registry.fail(item.run_id, "该任务类型尚未接入执行器", "EXECUTOR_NOT_IMPLEMENTED")
    return True


def main() -> None:
    logging.basicConfig(level=os.getenv("BANBOOS2_LOG_LEVEL", "INFO"))
    registry = build_registry()
    readonly_service = ReadonlyService()
    LOGGER.info("Banboos 2.0 worker started")
    while True:
        run_once(registry, readonly_service)


if __name__ == "__main__":
    main()
