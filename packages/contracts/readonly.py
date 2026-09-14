"""Versioned read-only contracts shared by the API, web shell and adapters."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class NodeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    province: str = ""


class PriceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    market: str
    start_date: date
    end_date: date
    valid_days: int = Field(ge=0)
    data_points: int = Field(ge=0)
    first_date: date | None = None
    last_date: date | None = None
    sources: list[str] = Field(default_factory=list)
    source_mode: str = "legacy-readonly"


class WeatherSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    observations: int = Field(ge=0)
    source: str | None = None
    avg_ghi_w_m2: float | None = None
    avg_wind_speed_m_s: float | None = None
    avg_temp_c: float | None = None
    source_mode: str = "legacy-readonly"


class RunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    kind: str
    status: str
    message: str = ""
    created_at: datetime
    completed_at: datetime | None = None
