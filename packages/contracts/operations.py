"""Read-only aggregate contract for the configured operations runtime."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, NonNegativeInt, computed_field


class TaskCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_status: dict[str, NonNegativeInt]

    @computed_field
    @property
    def total(self) -> int:
        return sum(self.by_status.values())


class TelemetryCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_points: NonNegativeInt
    pending_points: NonNegativeInt
    acknowledged_points: NonNegativeInt
    pending_batches: NonNegativeInt


class AlertCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: NonNegativeInt
    unacknowledged: NonNegativeInt
    acknowledged: NonNegativeInt
    unacknowledged_critical: NonNegativeInt
    unacknowledged_warning: NonNegativeInt


class EdgeCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry: TelemetryCounts
    alerts: AlertCounts


class OperationsSummary(EdgeCounts):
    schema_version: Literal["v1"] = "v1"
    scope: Literal["configured-runtime"] = "configured-runtime"
    collection_started_at: AwareDatetime
    generated_at: AwareDatetime
    data_mode: str
    node_count: NonNegativeInt
    task_counts: TaskCounts
    control_mode: Literal["disabled"] = "disabled"
