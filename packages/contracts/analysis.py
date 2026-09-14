"""Contracts for traceable market analysis jobs."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


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
    method: str = "disjoint-low-high-spread-estimate"
