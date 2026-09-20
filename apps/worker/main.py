"""Minimal worker for the phase-three task lifecycle.

The worker currently validates the queue and lifecycle contract. Real LP and
financial execution will be plugged in behind the same task kinds later.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from math import isclose

from packages.application.readonly_service import ReadonlyService
from packages.application.run_registry import RedisStateStore, RunRegistry
from packages.application.sqlite_runtime import SQLiteRuntime, runtime_path
from packages.application.task_queue import RedisTaskQueue
from packages.contracts.dispatch import DispatchParameters
from packages.contracts.dispatch_result import DispatchDayResult, DispatchRunResult
from packages.contracts.financial import FinancialTaskParameters
from packages.contracts.lp_analysis import LPAnalysisParameters, LPAnalysisRunResult
from packages.contracts.portfolio import PortfolioTaskParameters
from packages.contracts.portfolio_result import PortfolioResult
from packages.contracts.sensitivity import SensitivityTaskParameters
from packages.contracts.sensitivity_result import SensitivityPoint, SensitivityRunResult
from packages.domain.financial_model import MODEL_VERSION, FinancialError, calculate_financials
from packages.domain.lp_analysis import annual as lp_annual
from packages.domain.lp_analysis import compare as lp_compare
from packages.domain.lp_analysis import day_payload as lp_day_payload
from packages.domain.lp_analysis import monthly as lp_monthly
from packages.domain.lp_analysis import sensitivity as lp_sensitivity
from packages.domain.portfolio_optimizer import optimize_portfolio
from packages.domain.storage_dispatch import ALGORITHM_VERSION, DispatchError, solve_day
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots

LOGGER = logging.getLogger("banboos2.worker")


def build_registry() -> RunRegistry:
    redis_url = os.getenv("BANBOOS2_REDIS_URL")
    local_runtime = SQLiteRuntime(runtime_path()) if not redis_url else None
    return RunRegistry(RedisTaskQueue(redis_url) if redis_url else local_runtime,
                       RedisStateStore(redis_url) if redis_url else local_runtime)


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
            if result["valid_days"] == 0:
                raise ValueError("指定范围没有完整的96点有效日")
            registry.complete(item.run_id, "节点价差分析完成", result)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"节点价差分析失败：{error}", "PRICE_ANALYSIS_FAILED")
    elif item.kind == "lp-analysis":
        try:
            parameters = LPAnalysisParameters.model_validate(item.parameters)
            service = readonly_service or ReadonlyService()
            curves = service.dispatch_curves(parameters.node_id, parameters.market,
                                             parameters.start_date, parameters.end_date)
            if not curves:
                raise DispatchError("指定范围没有完整的96点有效日", "NO_VALID_PRICE_DAYS")
            snapshot_payload = {"kind": "lp-analysis", "algorithm_version": ALGORITHM_VERSION,
                                "parameters": parameters.model_dump(mode="json"), "curves": curves}
            snapshot_id = DispatchSnapshots().put(snapshot_payload)
            daily: list[dict] = []
            battery = parameters.battery()
            for index, curve in enumerate(curves, start=1):
                registry.update_progress(item.run_id, 5 + int(index / len(curves) * 80),
                                         f"正在求解第 {index}/{len(curves)} 个LP历史日")
                day = solve_day(curve["prices"], battery)
                daily.append(lp_day_payload(curve["run_date"], curve["prices"], day))
            total = sum(float(day["net_revenue_yuan"]) for day in daily)
            comparisons = lp_compare(daily, battery) if parameters.include_comparison else []
            sensitivity = []
            if parameters.include_sensitivity:
                registry.update_progress(item.run_id, 87, "正在计算C率敏感性情景")
                sensitivity = lp_sensitivity(curves, battery, parameters.c_rates, parameters.capex_per_mwh)
            result = LPAnalysisRunResult(
                node_id=parameters.node_id, market=parameters.market,
                start_date=parameters.start_date, end_date=parameters.end_date,
                power_mw=parameters.power_mw, capacity_mwh=parameters.capacity_mwh,
                duration_hours=battery.duration_hours, valid_days=len(daily),
                total_net_revenue_yuan=total,
                annualized_net_revenue_yuan=total / len(daily) * 365,
                snapshot_id=snapshot_id, algorithm_version=ALGORITHM_VERSION,
                days=daily, monthly=lp_monthly(daily), annual=lp_annual(daily),
                comparison=comparisons, sensitivity=sensitivity,
            )
            registry.complete(item.run_id, "LP详细历史回放完成", result.model_dump(mode="json"))
        except DispatchError as error:
            registry.fail(item.run_id, f"LP详细回放失败：{error}", error.code)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"LP详细回放失败：{error}", "LP_ANALYSIS_FAILED")
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
    elif item.kind == "financial":
        try:
            parameters = FinancialTaskParameters.model_validate(item.parameters)
            if parameters.annual_revenue_yuan is None and parameters.source_run_id:
                upstream = registry.get(parameters.source_run_id)
                if (not upstream or upstream.status != "succeeded" or not upstream.result
                        or upstream.kind not in {"strict-dispatch", "price-analysis"}):
                    raise FinancialError("上游价差或调度任务尚未成功，不能开始财务测算")
                for field in ("power_mw", "capacity_mwh"):
                    if not isclose(float(upstream.result.get(field, 0)), getattr(parameters, field),
                                   rel_tol=1e-9, abs_tol=1e-6):
                        raise FinancialError("财务功率和容量必须与上游分析规模一致，请重新分析或输入手动收益")
                revenue_key = ("annualized_revenue_yuan" if upstream.kind == "price-analysis"
                               else "annualized_net_revenue_yuan")
                annual_revenue = upstream.result.get(revenue_key)
                parameters = parameters.model_copy(update={"annual_revenue_yuan": annual_revenue})
            result = calculate_financials(parameters.financial())
            result["source_run_id"] = parameters.source_run_id
            result["input_parameters"] = parameters.model_dump(exclude_none=True)
            registry.complete(item.run_id, "财务现金流测算完成", result)
        except FinancialError as error:
            registry.fail(item.run_id, f"财务测算失败：{error}", "FINANCIAL_INPUT_INVALID")
        except (TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"财务测算失败：{error}", "FINANCIAL_FAILED")
    elif item.kind == "sensitivity":
        try:
            request = SensitivityTaskParameters.model_validate(item.parameters)
            base = request.base
            if base.annual_revenue_yuan is None and base.source_run_id:
                upstream = registry.get(base.source_run_id)
                if (not upstream or upstream.status != "succeeded" or not upstream.result
                        or upstream.kind not in {"strict-dispatch", "price-analysis"}):
                    raise FinancialError("上游价差或调度任务尚未成功，不能开始敏感性分析")
                for field in ("power_mw", "capacity_mwh"):
                    if not isclose(float(upstream.result.get(field, 0)), getattr(base, field),
                                   rel_tol=1e-9, abs_tol=1e-6):
                        raise FinancialError("敏感性分析规模必须与上游分析规模一致")
                revenue_key = ("annualized_revenue_yuan" if upstream.kind == "price-analysis"
                               else "annualized_net_revenue_yuan")
                base = base.model_copy(update={"annual_revenue_yuan": upstream.result.get(revenue_key)})
            baseline = base.financial()
            points = []
            for index, change in enumerate(request.change_rates, start=1):
                updates = {}
                current = getattr(baseline, request.variable)
                updates[request.variable] = (max(1, round(current * (1 + change)))
                                             if request.variable == "operation_years"
                                             else current * (1 + change))
                scenario = baseline.__class__(**{**baseline.__dict__, **updates})
                result = calculate_financials(scenario)
                points.append(SensitivityPoint(
                    change_rate=change, full_irr=result["full_irr"],
                    full_npv_yuan=result["full_npv_yuan"], payback_year=result["payback_year"],
                    first_year_net_profit_yuan=result["yearly"][0]["net_profit_yuan"],
                ))
                registry.update_progress(item.run_id, 5 + int(index / len(request.change_rates) * 90),
                                         f"正在计算第 {index}/{len(request.change_rates)} 个敏感性情景")
            result = SensitivityRunResult(
                variable=request.variable, base_power_mw=base.power_mw,
                base_capacity_mwh=base.capacity_mwh, source_run_id=base.source_run_id,
                model_version=MODEL_VERSION,
                points=points,
            )
            registry.complete(item.run_id, "财务敏感性分析完成", result.model_dump(mode="json"))
        except FinancialError as error:
            registry.fail(item.run_id, f"敏感性分析失败：{error}", "SENSITIVITY_INPUT_INVALID")
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"敏感性分析失败：{error}", "SENSITIVITY_FAILED")
    elif item.kind == "portfolio-optimization":
        try:
            parameters = PortfolioTaskParameters.model_validate(item.parameters)
            registry.update_progress(item.run_id, 20, "正在评估候选项目组合")
            result = PortfolioResult.model_validate(optimize_portfolio(parameters))
            registry.update_progress(item.run_id, 90, "正在整理组合收益与投资指标")
            registry.complete(item.run_id, result.message, result.model_dump(mode="json"))
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            registry.fail(item.run_id, f"组合优化失败：{error}", "PORTFOLIO_OPTIMIZATION_FAILED")
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
