"""Bounded, explicit historical MILP task inputs."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.domain.storage_dispatch import BatteryParameters


class DispatchParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    node_id: int = Field(gt=0)
    market: Literal["日前", "实时"]
    start_date: date
    end_date: date
    power_mw: float = Field(gt=0)
    capacity_mwh: float = Field(gt=0)
    eta_charge: float = Field(default=0.92, gt=0, le=1)
    eta_discharge: float = Field(default=0.92, gt=0, le=1)
    soc_min: float = 0.05
    soc_max: float = 0.95
    soc_initial: float = 0.50
    max_daily_cycles: float = Field(default=2, ge=0)
    hurdle_yuan_per_mwh: float = Field(default=50, ge=0)
    degradation_alpha: float = Field(default=0, ge=0)
    min_daily_revenue_yuan: float = Field(default=0, ge=0)
    line_loss_yuan_per_mwh: float = 20.7
    transmission_yuan_per_mwh: float = 150.3
    system_operation_yuan_per_mwh: float = 56.5
    cross_subsidy_yuan_per_mwh: float = 7.3

    def battery(self) -> BatteryParameters:
        return BatteryParameters(**self.model_dump(exclude={"node_id", "market", "start_date", "end_date"}))

    @model_validator(mode="after")
    def validate_request(self):
        if not 0 <= (self.end_date - self.start_date).days < 31:
            raise ValueError("每个历史调度任务须为1至31天，长期回放请分批提交")
        self.battery().validate()
        return self
