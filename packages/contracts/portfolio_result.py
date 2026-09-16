from pydantic import BaseModel, ConfigDict, Field


class PortfolioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str
    selected_projects: list[dict] = Field(default_factory=list)
    total_investment_wan: float = 0
    total_npv_wan: float = 0
    total_annual_revenue_wan: float = 0
    portfolio_irr: float | None = None
    algorithm_version: str
    outcome: str
    message: str
    cashflow_note: str
