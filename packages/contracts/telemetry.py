"""Canonical telemetry contract for the edge simulator and future gateways."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TelemetryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: str
    device_id: str
    point_id: str
    event_time: datetime
    ingest_time: datetime
    value: float
    unit: str
    quality_code: str = "good"
    source_protocol: str = "simulator"
    raw_message_id: str


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    points: list[TelemetryPoint] = Field(min_length=1)
