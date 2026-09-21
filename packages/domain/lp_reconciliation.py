"""Deterministic field-level checks for completed LP replay results."""
from __future__ import annotations

from math import isfinite

TOLERANCE = 0.05


def reconcile_lp(result: dict) -> dict:
    checks: list[dict] = []
    days = result.get("days") or []
    _check(checks, "daily_count", len(days), result.get("valid_days", 0), 0)
    total_daily = sum(float(day.get("net_revenue_yuan", 0)) for day in days)
    _check(checks, "total_net_revenue", total_daily, float(result.get("total_net_revenue_yuan", 0)), TOLERANCE)
    for day in days:
        prefix = str(day.get("run_date", "unknown"))
        trajectories = [day.get("prices_yuan_per_mwh"), day.get("charge_mw"), day.get("discharge_mw"), day.get("soc")]
        lengths = [len(values) if isinstance(values, list) else 0 for values in trajectories]
        _check(checks, f"{prefix}.trajectory_96", min(lengths) if lengths else 0, 96, 0)
        finite = all(isfinite(float(value)) for values in trajectories if isinstance(values, list) for value in values)
        _check(checks, f"{prefix}.finite_trajectory", 1 if finite else 0, 1, 0)
        soc = day.get("soc") or []
        soc_ok = all(-TOLERANCE <= float(value) <= 1 + TOLERANCE for value in soc)
        _check(checks, f"{prefix}.soc_bounds", 1 if soc_ok else 0, 1, 0)
        simultaneous = sum(1 for charge, discharge in zip(day.get("charge_mw") or [], day.get("discharge_mw") or [])
                           if float(charge) > TOLERANCE and float(discharge) > TOLERANCE)
        _check(checks, f"{prefix}.mutual_exclusion", simultaneous, 0, 0)
        # Losses, transmission and cross-subsidy are already embedded in the
        # charge/discharge prices by the solver.  The surcharge/refund fields
        # are explanatory components and must not be subtracted a second time.
        expected = (float(day.get("discharge_revenue_yuan", 0)) - float(day.get("charge_cost_yuan", 0))
                    - float(day.get("hurdle_cost_yuan", 0)) - float(day.get("degradation_cost_yuan", 0)))
        _check(checks, f"{prefix}.cashflow_identity", expected, float(day.get("net_revenue_yuan", 0)), TOLERANCE)
    _check_period_totals(checks, days, result.get("monthly") or [], "month", 7, "revenue_total_yuan")
    _check_period_totals(checks, days, result.get("annual") or [], "year", 4, "revenue_total_yuan")
    failed = [item for item in checks if item["status"] == "failed"]
    return {"status": "failed" if failed else "passed", "checks": checks,
            "valid_days": len(days), "algorithm_version": result.get("algorithm_version", "")}


def _check_period_totals(checks, days, aggregates, key, prefix_length, revenue_key):
    expected = {}
    for day in days:
        period = str(day.get("run_date", ""))[:prefix_length]
        expected[period] = expected.get(period, 0.0) + float(day.get("net_revenue_yuan", 0))
    actual = {str(row.get(key)): float(row.get(revenue_key, 0)) for row in aggregates}
    for period, value in expected.items():
        _check(checks, f"{period}.{revenue_key}", value, actual.get(period, 0.0), TOLERANCE)


def _check(checks, name: str, actual: float, expected: float, tolerance: float):
    delta = float(actual) - float(expected)
    checks.append({"name": name, "status": "passed" if abs(delta) <= tolerance else "failed",
                   "actual": actual, "expected": expected, "delta": delta, "tolerance": tolerance})
