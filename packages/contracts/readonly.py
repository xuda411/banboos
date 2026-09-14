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


class PriceRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    market: str
    first_date: date | None = None
    last_date: date | None = None
    source_mode: str = "legacy-readonly"


class PriceCurve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    market: str
    run_date: date
    prices: list[float] = Field(min_length=96, max_length=96)
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


class WeatherObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    data_time: datetime
    source: str | None = None
    ghi_w_m2: float | None = None
    wind_speed_m_s: float | None = None
    temp_c: float | None = None
    pv_predict_power_mw: float | None = None
    wind_predict_power_mw: float | None = None
    source_mode: str = "legacy-readonly"
    is_power_simulated: bool = True


class DataQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int
    market: str
    start_date: date
    end_date: date
    total_records: int = Field(ge=0)
    complete_records: int = Field(ge=0)
    incomplete_records: int = Field(ge=0)
    missing_cells: int = Field(ge=0)
    non_finite_cells: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)
    source_mode: str = "legacy-readonly"


class RunStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    kind: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    error_code: str | None = None
    parameters: dict = Field(default_factory=dict)
    result: dict | None = None
    created_at: datetime
    completed_at: datetime | None = None
