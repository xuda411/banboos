"""Result contract for strict historical dispatch replay."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DispatchDayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_date: date
    net_revenue_yuan: float
    charge_energy_mwh: float
    discharge_energy_mwh: float
    cycles: float
    shutdown: bool
    solver_gap: float


class DispatchRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    market: str
    start_date: date
    end_date: date
    power_mw: float
    capacity_mwh: float
    duration_hours: float
    valid_days: int = Field(ge=0)
    total_net_revenue_yuan: float
    annualized_net_revenue_yuan: float
    snapshot_id: str
    algorithm_version: str
    historical_replay: bool = True
    days: list[DispatchDayResult] = Field(default_factory=list)
