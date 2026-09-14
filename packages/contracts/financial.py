"""Financial task contracts; monetary values are yuan unless stated otherwise."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.domain.financial_model import FinancialParameters


class FinancialTaskParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    power_mw: float = Field(gt=0)
    capacity_mwh: float = Field(gt=0)
    annual_revenue_yuan: float | None = Field(default=None, ge=0)
    capex_yuan_per_wh: float = Field(default=1.2, gt=0)
    operation_years: int = Field(default=25, ge=1, le=100)
    om_rate: float = Field(default=0.0075, ge=0, le=1)
    om_growth: float = Field(default=0.01, ge=0, le=1)
    first_year_eol: float = Field(default=0.97, gt=0, le=1)
    final_eol: float = Field(default=0.80, gt=0, le=1)
    residual_rate: float = Field(default=0.02, ge=0, le=1)
    income_tax_rate: float = Field(default=0.25, ge=0, le=1)
    discount_rate: float = 0.08
    source_run_id: str | None = None

    def financial(self) -> FinancialParameters:
        if self.annual_revenue_yuan is None:
            raise ValueError("annual_revenue_yuan or source_run_id is required")
        return FinancialParameters(**self.model_dump(exclude={"source_run_id"}))

    @model_validator(mode="after")
    def validate_parameters(self):
        if self.annual_revenue_yuan is None and not self.source_run_id:
            raise ValueError("annual_revenue_yuan or source_run_id is required")
        if self.annual_revenue_yuan is not None:
            self.financial().validate()
        return self
