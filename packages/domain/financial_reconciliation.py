"""Pure integrity checks for a completed financial calculation."""
from __future__ import annotations

from math import isclose

from packages.domain.financial_model import irr, npv


def reconcile_financial(result: dict, parameters: dict) -> dict:
    checks = []
    cashflows = [float(value) for value in result.get("cashflows_yuan", [])]
    equity = [float(value) for value in result.get("equity_cashflows_yuan", [])]
    yearly = result.get("yearly") or []
    rate = float(parameters.get("discount_rate", 0.08))
    _check(checks, "cashflow_length", len(cashflows), len(yearly) + 1, 0)
    _check(checks, "equity_cashflow_length", len(equity), len(cashflows), 0)
    _check(checks, "project_npv", npv(rate, cashflows), float(result.get("full_npv_yuan", 0)), 0.05)
    _check(checks, "equity_npv", npv(rate, equity), float(result.get("equity_npv_yuan", 0)), 0.05)
    _check_optional(checks, "project_irr", irr(cashflows), result.get("full_irr"), 1e-7)
    _check_optional(checks, "equity_irr", irr(equity), result.get("equity_irr"), 1e-7)
    _check(checks, "initial_investment", -cashflows[0] if cashflows else 0,
           float(result.get("total_investment_yuan", 0)), 0.05)
    for index, row in enumerate(yearly, start=1):
        _check(checks, f"year_{index}.project_cashflow", float(row.get("project_cashflow_yuan", 0)),
               cashflows[index] if index < len(cashflows) else 0, 0.05)
        _check(checks, f"year_{index}.equity_cashflow", float(row.get("equity_cashflow_yuan", 0)),
               equity[index] if index < len(equity) else 0, 0.05)
    failed = sum(item["status"] == "failed" for item in checks)
    return {"status": "failed" if failed else "passed", "checks": checks,
            "model_version": result.get("model_version", ""), "years": len(yearly)}


def _check(checks, name, actual, expected, tolerance):
    delta = float(actual) - float(expected)
    checks.append({"name": name, "status": "passed" if isclose(float(actual), float(expected),
                   abs_tol=tolerance, rel_tol=1e-9) else "failed",
                   "actual": float(actual), "expected": float(expected), "delta": delta,
                   "tolerance": tolerance})


def _check_optional(checks, name, actual, expected, tolerance):
    if actual is None or expected is None:
        checks.append({"name": name, "status": "passed", "actual": actual or 0.0,
                       "expected": expected or 0.0, "delta": 0.0, "tolerance": tolerance})
        return
    _check(checks, name, actual, expected, tolerance)
