"""Contracts for traceable market analysis jobs."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PriceBaselineMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str = Field(min_length=7, max_length=7)
    valid_days: int = Field(ge=0)
    charge_price_yuan_per_mwh: float
    discharge_price_yuan_per_mwh: float
    spread_yuan_per_mwh: float


class PriceAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    market: str
    start_date: date
    end_date: date
    power_mw: float = Field(gt=0)
    capacity_mwh: float = Field(gt=0)
    duration_hours: float = Field(gt=0)
    valid_days: int = Field(ge=0)
    average_daily_revenue_yuan: float = Field(ge=0)
    annualized_revenue_yuan: float = Field(ge=0)
    source_mode: str
    charge_price_yuan_per_mwh: float
    discharge_price_yuan_per_mwh: float
    spread_yuan_per_mwh: float
    available_days: int = Field(ge=0)
    excluded_records: int = Field(ge=0)
    multiple_source_days: int = Field(ge=0)
    baseline_policy: str
    snapshot_id: str
    monthly: list[PriceBaselineMonth] = Field(default_factory=list)
    method: str = "annual_valid_day_window_mean_v1"
