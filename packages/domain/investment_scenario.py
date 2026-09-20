"""Domain calculation for explicit future investment scenarios."""
from __future__ import annotations

SCENARIO_VERSION = "investment_scenario_v1"


def build_investment_scenario(baseline: dict, parameters: dict, scenario_run_id: str) -> dict:
    """Build a traceable annual revenue scenario from a completed price analysis.

    The baseline analysis already includes the selected duration and round-trip
    efficiency. Scenario controls are applied once here; the financial model
    remains responsible for year-by-year degradation and cash-flow details.
    """
    average_daily = float(baseline["average_daily_revenue_yuan"])
    annual_cycles = float(parameters["annual_cycles"])
    utilization = float(parameters["utilization"])
    spread_factor = float(parameters["spread_factor"])
    retention_rate = float(parameters["retention_rate"])
    annual_revenue = max(0.0, average_daily * annual_cycles * utilization * spread_factor * retention_rate)
    return {
        "scenario_name": parameters["scenario_name"],
        "source_run_id": parameters["source_run_id"],
        "source_snapshot_id": baseline.get("snapshot_id"),
        "node_id": baseline["node_id"], "market": baseline["market"],
        "start_date": baseline["start_date"], "end_date": baseline["end_date"],
        "power_mw": baseline["power_mw"], "capacity_mwh": baseline["capacity_mwh"],
        "duration_hours": baseline["duration_hours"],
        "baseline_spread_yuan_per_mwh": baseline["spread_yuan_per_mwh"],
        "average_daily_revenue_yuan": average_daily,
        "annual_cycles": annual_cycles, "utilization": utilization,
        "spread_factor": spread_factor, "retention_rate": retention_rate,
        "annual_revenue_yuan": annual_revenue,
        "annualized_revenue_yuan": annual_revenue,
        "formula": "average_daily_revenue_yuan × annual_cycles × utilization × spread_factor × retention_rate",
        "financial_parameters": {
            "power_mw": baseline["power_mw"], "capacity_mwh": baseline["capacity_mwh"],
            "annual_revenue_yuan": annual_revenue, "source_run_id": scenario_run_id,
        },
        "algorithm_version": SCENARIO_VERSION,
    }
