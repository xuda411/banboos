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
from packages.contracts.dispatch import DispatchParameters
from packages.contracts.dispatch_result import DispatchDayResult, DispatchRunResult
from packages.domain.storage_dispatch import ALGORITHM_VERSION, DispatchError, solve_day
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots

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
    elif item.kind == "strict-dispatch":
        try:
            parameters = DispatchParameters.model_validate(item.parameters)
            service = readonly_service or ReadonlyService()
            curves = service.dispatch_curves(parameters.node_id, parameters.market,
                                             parameters.start_date, parameters.end_date)
            if not curves:
                raise DispatchError("指定范围没有完整的96点有效日", "NO_VALID_PRICE_DAYS")
            snapshot_payload = {"algorithm_version": ALGORITHM_VERSION,
                                "parameters": parameters.model_dump(mode="json"), "curves": curves}
            snapshot_id = DispatchSnapshots().put(snapshot_payload)
            daily: list[DispatchDayResult] = []
            for index, curve in enumerate(curves, start=1):
                registry.update_progress(item.run_id, 5 + int(index / len(curves) * 90),
                                         f"正在求解第 {index}/{len(curves)} 个历史日")
                day = solve_day(curve["prices"], parameters.battery())
                daily.append(DispatchDayResult(
                    run_date=curve["run_date"], net_revenue_yuan=day.net_revenue_yuan,
                    charge_energy_mwh=day.charge_energy_mwh,
                    discharge_energy_mwh=day.discharge_energy_mwh, cycles=day.cycles,
                    shutdown=day.shutdown, solver_gap=day.solver_gap,
                ))
            total = sum(day.net_revenue_yuan for day in daily)
            result = DispatchRunResult(
                node_id=parameters.node_id, market=parameters.market,
                start_date=parameters.start_date, end_date=parameters.end_date,
                power_mw=parameters.power_mw, capacity_mwh=parameters.capacity_mwh,
                duration_hours=parameters.battery().duration_hours, valid_days=len(daily),
                total_net_revenue_yuan=total, annualized_net_revenue_yuan=total / len(daily) * 365,
                snapshot_id=snapshot_id, algorithm_version=ALGORITHM_VERSION, days=daily,
            )
            registry.complete(item.run_id, "严格互斥历史调度回放完成", result.model_dump(mode="json"))
        except DispatchError as error:
            registry.fail(item.run_id, f"严格调度失败：{error}", error.code)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"严格调度失败：{error}", "DISPATCH_FAILED")
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
