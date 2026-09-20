"""Pure aggregation and report helpers for the detailed LP replay."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from itertools import pairwise

from packages.domain.storage_dispatch import BatteryParameters, DispatchResult, solve_day


def day_payload(run_date: str, prices: list[float], result: DispatchResult, p: BatteryParameters) -> dict:
    spread = max(prices) - min(prices)
    average_step = sum(abs(b - a) for a, b in pairwise(prices)) / 95
    return {
        "run_date": run_date, "prices_yuan_per_mwh": prices,
        "charge_mw": result.charge_mw, "discharge_mw": result.discharge_mw, "soc": result.soc,
        "charge_energy_mwh": result.charge_energy_mwh,
        "discharge_energy_mwh": result.discharge_energy_mwh,
        "charge_cost_yuan": result.charge_cost_yuan,
        "discharge_revenue_yuan": result.discharge_revenue_yuan,
        "surcharge_cost_yuan": result.charge_energy_mwh * (p.line_loss_yuan_per_mwh + p.transmission_yuan_per_mwh + p.system_operation_yuan_per_mwh),
        "refund_revenue_yuan": result.discharge_energy_mwh * (p.transmission_yuan_per_mwh + p.cross_subsidy_yuan_per_mwh),
        "hurdle_cost_yuan": result.hurdle_cost_yuan,
        "degradation_cost_yuan": result.degradation_cost_yuan,
        "net_revenue_yuan": result.net_revenue_yuan, "cycles": result.cycles,
        "spread_max_yuan_per_mwh": spread, "spread_avg_yuan_per_mwh": average_step,
        "shutdown": result.shutdown, "solver_gap": result.solver_gap,
        "degradation_approximation_bound_yuan": result.degradation_approximation_bound_yuan,
        "simultaneous_slots": 0,
        "model_note": "96段严格互斥MILP历史回放；日末SOC复位；结果不是预测或实际运营收益",
        "message": "OK",
        "success": True,
    }


def _aggregate(days: Iterable[dict], key: str, average_revenue_key: str, prefix_length: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for day in days:
        grouped.setdefault(str(day["run_date"])[:prefix_length], []).append(day)
    rows = []
    for period, values in sorted(grouped.items()):
        revenue = sum(float(item["net_revenue_yuan"]) for item in values)
        rows.append({
            key: period, "days": len(values),
            "revenue_total_yuan": round(revenue, 2),
            average_revenue_key: round(revenue / len(values), 2),
            "discharge_energy_total_mwh": round(sum(float(item["discharge_energy_mwh"]) for item in values), 3),
            "cycles_avg": round(sum(float(item["cycles"]) for item in values) / len(values), 4),
            "spread_max_yuan_per_mwh": round(max(float(item["spread_max_yuan_per_mwh"]) for item in values), 3),
            "spread_avg_yuan_per_mwh": round(sum(float(item["spread_avg_yuan_per_mwh"]) for item in values) / len(values), 3),
        })
    return rows


def monthly(days: list[dict]) -> list[dict]:
    return _aggregate(days, "month", "revenue_avg_yuan", 7)


def annual(days: list[dict]) -> list[dict]:
    return _aggregate(days, "year", "revenue_avg_daily_yuan", 4)


def simple_window(prices: list[float], p: BatteryParameters) -> dict:
    """Desktop 1.6.6 continuous-window baseline used by the comparison view."""
    n = max(1, round(p.capacity_mwh / p.power_mw / 0.25))
    charge_eff = [x + p.line_loss_yuan_per_mwh + p.transmission_yuan_per_mwh + p.system_operation_yuan_per_mwh for x in prices]
    discharge_eff = [x + p.transmission_yuan_per_mwh + p.cross_subsidy_yuan_per_mwh for x in prices]
    best = {"revenue": 0.0, "discharge": 0.0, "cycles": 0.0}
    for ch_start in range(97 - n):
        ch_price = sum(charge_eff[ch_start:ch_start + n]) / n
        for dis_start in range(97 - n):
            if not (ch_start + n <= dis_start or dis_start + n <= ch_start):
                continue
            dis_price = sum(discharge_eff[dis_start:dis_start + n]) / n
            efficiency = p.eta_charge * p.eta_discharge
            room = p.capacity_mwh * ((p.soc_max - p.soc_initial) if ch_start < dis_start else (p.soc_initial - p.soc_min))
            hours = n * 0.25
            cycle_cap = 2 * p.capacity_mwh * p.max_daily_cycles / (1 + efficiency)
            energy = min(p.power_mw * hours, p.power_mw * hours / efficiency,
                         room / p.eta_charge, cycle_cap)
            margin = (dis_price - p.hurdle_yuan_per_mwh) * efficiency - ch_price
            if margin <= 0:
                continue
            revenue = margin * energy
            if revenue > best["revenue"] and revenue >= p.min_daily_revenue_yuan:
                best = {"revenue": revenue, "discharge": energy * efficiency,
                        "cycles": (energy + energy * efficiency) / (2 * p.capacity_mwh)}
    return best


def compare(days: list[dict], p: BatteryParameters) -> list[dict]:
    rows = []
    for day in days:
        baseline = simple_window(day["prices_yuan_per_mwh"], p)
        lp = float(day["net_revenue_yuan"])
        simple = float(baseline["revenue"])
        improvement = lp - simple
        rows.append({"run_date": day["run_date"], "lp_revenue_yuan": lp,
                     "simple_revenue_yuan": simple, "improvement_yuan": improvement,
                     "improvement_pct": improvement / simple * 100 if simple else 0.0,
                     "lp_discharge_energy_mwh": day["discharge_energy_mwh"],
                     "simple_discharge_energy_mwh": baseline["discharge"],
                     "lp_cycles": day["cycles"]})
    return rows


def sensitivity(curves: list[dict], p: BatteryParameters, c_rates: list[float], capex_per_mwh: float) -> list[dict]:
    rows = []
    for c_rate in c_rates:
        if c_rate <= 0:
            continue
        current = replace(p, power_mw=p.capacity_mwh * c_rate)
        results = [solve_day(curve["prices"], current) for curve in curves]
        revenue = sum(item.net_revenue_yuan for item in results)
        count = len(results)
        rows.append({"c_rate": c_rate, "power_mw": current.power_mw,
                     "capacity_mwh": current.capacity_mwh,
                     "total_revenue_yuan": revenue,
                     "avg_daily_revenue_yuan": revenue / count if count else 0.0,
                     "annual_revenue_yuan": revenue / count * 365 if count else 0.0,
                     "avg_cycles": sum(item.cycles for item in results) / count if count else 0.0,
                     "capex_yuan": current.capacity_mwh * capex_per_mwh})
    return rows
