from pydantic import BaseModel, ConfigDict, Field


class PortfolioCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    node_id: int
    province: str = ""
    market: str
    capacity_mwh: float = Field(gt=0)
    unit_investment_yuan_wh: float = Field(gt=0)
    annual_revenue_wan: float = Field(ge=0)
    spread_yuan_per_mwh: float
    valid_days: int = Field(ge=0)
    source_mode: str
