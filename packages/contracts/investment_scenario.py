"""Explicit investment-scenario contract built from a completed price analysis."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvestmentScenarioParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source_run_id: str = Field(min_length=36, max_length=80)
    scenario_name: str = Field(default="基准情景", min_length=1, max_length=80)
    spread_factor: float = Field(default=1.0, gt=0, le=10)
    annual_cycles: float = Field(default=350, ge=0, le=2000)
    utilization: float = Field(default=1.0, ge=0, le=1)
    retention_rate: float = Field(default=1.0, gt=0, le=1)

    @field_validator("scenario_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("情景名称不能为空")
        return value

