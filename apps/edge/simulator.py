"""Deterministic station simulator used before any real device connection."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import uuid4

from packages.contracts.telemetry import TelemetryBatch, TelemetryPoint


def generate_batch(station_id: str = "demo-station", at: datetime | None = None,
                   step_minutes: int = 5) -> TelemetryBatch:
    timestamp = at or datetime.now(UTC)
    phase = (timestamp.hour * 60 + timestamp.minute) / 1440 * math.tau
    soc = 55.0 + 20.0 * math.sin(phase)
    power = 10.0 * math.sin(phase + math.pi / 2)
    points = [
        _point(station_id, "pcs-01", "soc", timestamp, soc, "%"),
        _point(station_id, "pcs-01", "active_power", timestamp, power, "MW"),
        _point(station_id, "bms-01", "temperature", timestamp, 25.0 + 2.0 * math.sin(phase), "°C"),
    ]
    return TelemetryBatch(batch_id=str(uuid4()), points=points)


def _point(station_id: str, device_id: str, point_id: str, event_time: datetime,
           value: float, unit: str) -> TelemetryPoint:
    return TelemetryPoint(
        station_id=station_id,
        device_id=device_id,
        point_id=point_id,
        event_time=event_time,
        ingest_time=datetime.now(UTC),
        value=round(value, 4),
        unit=unit,
        raw_message_id=str(uuid4()),
    )
