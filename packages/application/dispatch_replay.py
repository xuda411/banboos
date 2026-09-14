"""Deterministic replay of a content-addressed strict-dispatch snapshot."""
from __future__ import annotations

from packages.contracts.dispatch import DispatchParameters
from packages.contracts.dispatch_result import DispatchDayResult, DispatchRunResult
from packages.domain.storage_dispatch import ALGORITHM_VERSION, solve_day
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots


def replay(snapshot_id: str, snapshots: DispatchSnapshots | None = None) -> DispatchRunResult:
    store = snapshots or DispatchSnapshots()
    payload = store.read(snapshot_id)
    parameters = DispatchParameters.model_validate(payload["parameters"])
    daily: list[DispatchDayResult] = []
    for curve in payload["curves"]:
        result = solve_day(curve["prices"], parameters.battery())
        daily.append(DispatchDayResult(
            run_date=curve["run_date"], net_revenue_yuan=result.net_revenue_yuan,
            charge_energy_mwh=result.charge_energy_mwh,
            discharge_energy_mwh=result.discharge_energy_mwh, cycles=result.cycles,
            shutdown=result.shutdown, solver_gap=result.solver_gap,
        ))
    total = sum(day.net_revenue_yuan for day in daily)
    return DispatchRunResult(
        node_id=parameters.node_id, market=parameters.market,
        start_date=parameters.start_date, end_date=parameters.end_date,
        power_mw=parameters.power_mw, capacity_mwh=parameters.capacity_mwh,
        duration_hours=parameters.battery().duration_hours, valid_days=len(daily),
        total_net_revenue_yuan=total,
        annualized_net_revenue_yuan=total / len(daily) * 365 if daily else 0,
        snapshot_id=snapshot_id, algorithm_version=ALGORITHM_VERSION, days=daily,
    )
