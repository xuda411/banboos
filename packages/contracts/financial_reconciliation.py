from pydantic import BaseModel, ConfigDict, Field


class FinancialReconciliationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    actual: float
    expected: float
    delta: float
    tolerance: float = Field(ge=0)


class FinancialReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    kind: str = "financial"
    status: str
    years: int = Field(ge=0)
    model_version: str
    checks: list[FinancialReconciliationCheck] = Field(default_factory=list)
