from pydantic import BaseModel, ConfigDict, Field


class LPReconciliationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    actual: float
    expected: float
    delta: float
    tolerance: float = Field(ge=0)


class LPReconciliationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    kind: str = "lp-analysis"
    status: str
    valid_days: int = Field(ge=0)
    algorithm_version: str
    checks: list[LPReconciliationCheck] = Field(default_factory=list)
