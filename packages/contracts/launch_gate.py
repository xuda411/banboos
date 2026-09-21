from pydantic import BaseModel, ConfigDict


class LaunchGateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    detail: str


class LaunchGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    environment: str
    control_mode: str
    checks: list[LaunchGateCheck]
