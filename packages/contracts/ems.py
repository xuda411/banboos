"""EMS decision and feedback contracts for simulation and future adapters."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

EMSPlanStatus = Literal["draft", "approved", "sent", "failed", "cancelled"]
EMSDeliveryStatus = Literal[
    "preview-only", "awaiting-approval", "simulated", "adapter-not-configured",
    "blocked-control-disabled",
]
EMSOperationMode = Literal["simulation", "adapter"]
EMSPointMode = Literal["charge", "discharge", "idle"]


class EMSDecisionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    event_time: AwareDatetime
    power_mw: float = Field(ge=-5000, le=5000)
    price_yuan_per_mwh: float = Field(ge=0, le=10000)
    mode: EMSPointMode


class EMSDecisionPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: str = Field(min_length=1, max_length=120)
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    points: list[EMSDecisionPoint] = Field(min_length=1, max_length=288)
    source_run_id: str | None = Field(default=None, max_length=160)
    algorithm_version: str = Field(default="ems-simulation-v1", min_length=1, max_length=80)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_window(self):
        if self.valid_to <= self.valid_from:
            raise ValueError("决策计划结束时间必须晚于开始时间")
        times = [point.event_time for point in self.points]
        if any(value < self.valid_from or value > self.valid_to for value in times):
            raise ValueError("决策点必须位于计划有效时间范围内")
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError("决策点必须按时间升序且不能重复")
        for point in self.points:
            if point.mode == "charge" and point.power_mw > 0:
                raise ValueError("充电功率必须为负值")
            if point.mode == "discharge" and point.power_mw < 0:
                raise ValueError("放电功率必须为正值")
            if point.mode == "idle" and abs(point.power_mw) > 1e-9:
                raise ValueError("待机功率必须为零")
        return self


class EMSDecisionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    station_id: str
    status: EMSPlanStatus
    delivery_status: EMSDeliveryStatus
    operation_mode: EMSOperationMode
    control_mode: str
    created_at: datetime
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    points: list[EMSDecisionPoint]
    source_run_id: str | None = None
    algorithm_version: str
    note: str = ""


class EMSFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    station_id: str = Field(min_length=1, max_length=120)
    plan_id: UUID | None = None
    event_time: AwareDatetime
    actual_power_mw: float = Field(ge=-5000, le=5000)
    soc_pct: float = Field(ge=0, le=100)
    actual_price_yuan_per_mwh: float | None = Field(default=None, ge=0, le=10000)
    operating_state: Literal["charging", "discharging", "idle", "fault", "offline", "simulated"]
    quality_code: str = Field(default="good", min_length=1, max_length=32)
    raw_message_id: str = Field(min_length=1, max_length=160)


class EMSFeedback(EMSFeedbackRequest):
    received_at: datetime


class EMSDashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: str
    generated_at: datetime
    control_mode: str
    operation_mode: EMSOperationMode
    plan: EMSDecisionPlan | None = None
    latest_feedback: EMSFeedback | None = None
    target_power_mw: float | None = None
    target_price_yuan_per_mwh: float | None = None
    power_deviation_mw: float | None = None
    price_deviation_yuan_per_mwh: float | None = None
    feedback_count: int = Field(ge=0)
    feedback_status: Literal["no-feedback", "current", "delayed"]

