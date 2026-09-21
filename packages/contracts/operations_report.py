from pydantic import BaseModel, ConfigDict, Field


class OperationsReportPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str
    node_count: int = Field(ge=0)
    valid_days: int = Field(ge=0)
    average_spread_yuan_per_mwh: float


class OperationsReportProvince(BaseModel):
    model_config = ConfigDict(extra="forbid")

    province: str
    node_count: int = Field(ge=0)
    valid_nodes: int = Field(ge=0)
    valid_days: int = Field(ge=0)
    data_points: int = Field(ge=0)


class OperationsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: str
    start_date: str
    end_date: str
    duration_hours: float = Field(gt=0)
    node_count: int = Field(ge=0)
    valid_nodes: int = Field(ge=0)
    total_valid_days: int = Field(ge=0)
    total_data_points: int = Field(ge=0)
    provinces: list[OperationsReportProvince] = Field(default_factory=list)
    monthly: list[OperationsReportPeriod] = Field(default_factory=list)
    source_mode: str
