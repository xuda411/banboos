"""Contract for traceable multi-point financial sensitivity tasks."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.contracts.financial import FinancialTaskParameters


class SensitivityTaskParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    base: FinancialTaskParameters
    variable: Literal[
        "annual_revenue_yuan", "capex_yuan_per_wh", "om_rate", "discount_rate",
        "loan_rate", "operation_years"
    ]
    change_rates: list[float] = Field(min_length=3, max_length=9)

    @field_validator("change_rates")
    @classmethod
    def validate_rates(cls, values: list[float]) -> list[float]:
        if len({float(value) for value in values}) != len(values):
            raise ValueError("敏感性变动幅度不能重复")
        if any(value < -1 or value > 1 for value in values):
            raise ValueError("敏感性变动幅度须在-100%至100%之间")
        return sorted(values)
