"""Explainable telemetry checks for the read-only operations layer."""
from __future__ import annotations

from packages.contracts.telemetry import TelemetryAlert, TelemetryBatch


def evaluate_alerts(batch: TelemetryBatch) -> list[TelemetryAlert]:
    alerts: list[TelemetryAlert] = []
    for point in batch.points:
        code: str | None = None
        severity = "warning"
        message = ""
        if point.quality_code != "good":
            code, message = "TELEMETRY_QUALITY", f"质量码为 {point.quality_code}"
        elif point.point_id.lower() == "soc" and not 0 <= point.value <= 100:
            code, severity, message = "SOC_OUT_OF_RANGE", "critical", f"SOC 超出 0% 至 100% 范围：{point.value:g}%"
        elif point.point_id.lower() in {"temperature", "temp"} and point.value > 60:
            code, severity, message = "TEMPERATURE_HIGH", "critical", f"温度超过 60°C：{point.value:g}°C"
        elif point.point_id.lower() in {"temperature", "temp"} and point.value > 45:
            code, message = "TEMPERATURE_HIGH", f"温度超过关注阈值 45°C：{point.value:g}°C"
        if code:
            alerts.append(TelemetryAlert(code=code, severity=severity, station_id=point.station_id,
                                         device_id=point.device_id, point_id=point.point_id,
                                         event_time=point.event_time, message=message))
    return alerts
