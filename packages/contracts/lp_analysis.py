"""Contracts for the detailed 1.6.6-compatible LP historical replay."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.contracts.dispatch import DispatchParameters
from packages.domain.storage_dispatch import BatteryParameters


class LPAnalysisParameters(DispatchParameters):
    """Strict LP inputs plus the optional desktop-style comparison reports."""

    include_comparison: bool = True
    include_sensitivity: bool = False
    c_rates: list[float] = Field(default_factory=lambda: [0.25, 0.5, 0.75, 1.0, 1.5, 2.0])
    capex_per_mwh: float = Field(default=1_500_000, gt=0)

    def battery(self):
        fields = {
            "power_mw", "capacity_mwh", "eta_charge", "eta_discharge", "soc_min",
            "soc_max", "soc_initial", "max_daily_cycles", "hurdle_yuan_per_mwh",
            "degradation_alpha", "min_daily_revenue_yuan", "line_loss_yuan_per_mwh",
            "transmission_yuan_per_mwh", "system_operation_yuan_per_mwh",
            "cross_subsidy_yuan_per_mwh",
        }
        return BatteryParameters(**{key: getattr(self, key) for key in fields})

    @model_validator(mode="after")
    def validate_report_options(self):
        if not self.c_rates or any(rate <= 0 for rate in self.c_rates):
            raise ValueError("c_rates 必须为正数列表")
        if len(self.c_rates) > 8:
            raise ValueError("单次敏感性分析最多支持8个C率")
        return self


class LPDayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_date: date
    prices_yuan_per_mwh: list[float] = Field(min_length=96, max_length=96)
    charge_mw: list[float] = Field(min_length=96, max_length=96)
    discharge_mw: list[float] = Field(min_length=96, max_length=96)
    soc: list[float] = Field(min_length=96, max_length=96)
    charge_energy_mwh: float
    discharge_energy_mwh: float
    charge_cost_yuan: float
    discharge_revenue_yuan: float
    hurdle_cost_yuan: float
    degradation_cost_yuan: float
    net_revenue_yuan: float
    cycles: float
    spread_max_yuan_per_mwh: float
    spread_avg_yuan_per_mwh: float
    shutdown: bool
    solver_gap: float
    degradation_approximation_bound_yuan: float


class LPComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_date: date
    lp_revenue_yuan: float
    simple_revenue_yuan: float
    improvement_yuan: float
    improvement_pct: float
    lp_discharge_energy_mwh: float
    simple_discharge_energy_mwh: float
    lp_cycles: float


class LPSensitivityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    c_rate: float
    power_mw: float
    capacity_mwh: float
    total_revenue_yuan: float
    avg_daily_revenue_yuan: float
    annual_revenue_yuan: float
    avg_cycles: float
    capex_yuan: float


class LPAggregateMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str
    days: int
    revenue_total_yuan: float
    revenue_avg_yuan: float
    discharge_energy_total_mwh: float
    cycles_avg: float
    spread_max_yuan_per_mwh: float
    spread_avg_yuan_per_mwh: float


class LPAggregateYear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: str
    days: int
    revenue_total_yuan: float
    revenue_avg_daily_yuan: float
    discharge_energy_total_mwh: float
    cycles_avg: float
    spread_max_yuan_per_mwh: float
    spread_avg_yuan_per_mwh: float


class LPAnalysisRunResult(BaseModel):
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
    days: list[LPDayResult] = Field(default_factory=list)
    monthly: list[LPAggregateMonth] = Field(default_factory=list)
    annual: list[LPAggregateYear] = Field(default_factory=list)
    comparison: list[LPComparisonResult] = Field(default_factory=list)
    sensitivity: list[LPSensitivityPoint] = Field(default_factory=list)
