from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioSnapshotOptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    budget_limit_wan: float | None = Field(default=None, gt=0)
    revenue_target_wan: float | None = Field(default=None, gt=0)
    discount_rate: float = Field(default=0.08, ge=0, le=1)
    operation_years: int = Field(default=15, ge=1, le=100)
    node_ids: list[int] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_objective(self):
        if self.objective not in {"max_npv", "max_irr", "min_investment"}:
            raise ValueError("objective 无效")
        if self.objective in {"max_npv", "max_irr"} and self.budget_limit_wan is None:
            raise ValueError("最大 NPV / IRR 目标必须填写预算上限")
        if self.objective == "min_investment" and self.revenue_target_wan is None:
            raise ValueError("最小投资目标必须填写年净现金流目标")
        return self
