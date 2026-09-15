"""Published result for a financial sensitivity task."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SensitivityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_rate: float
    full_irr: float | None = None
    full_npv_yuan: float
    payback_year: float | None = None
    first_year_net_profit_yuan: float


class SensitivityRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variable: str
    base_power_mw: float = Field(gt=0)
    base_capacity_mwh: float = Field(gt=0)
    source_run_id: str | None = None
    model_version: str
    points: list[SensitivityPoint] = Field(min_length=3, max_length=9)
