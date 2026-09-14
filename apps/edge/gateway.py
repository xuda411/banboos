"""Durable, offline-first telemetry spool for the edge gateway.

The spool is deliberately local and append-only from the gateway's point of
view: reconnecting can replay pending batches in event-time order, while the
unique raw message id makes retries safe. It does not contain any production
control path.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from packages.contracts.telemetry import TelemetryAlert, TelemetryBatch


class TelemetrySpool:
    """SQLite-backed telemetry buffer that survives process restarts."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS telemetry_spool ("
                "raw_message_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, "
                "event_time TEXT NOT NULL, payload TEXT NOT NULL, acked INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_spool_pending_event "
                "ON telemetry_spool(acked, event_time, batch_id)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS telemetry_alerts ("
                "alert_id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                "acknowledged INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
            )

    def ingest(self, batch: TelemetryBatch) -> int:
        """Append a batch and return the number of newly accepted points."""
        accepted = 0
        with self._connect() as connection:
            for point in batch.points:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO telemetry_spool "
                    "(raw_message_id, batch_id, event_time, payload) VALUES (?, ?, ?, ?)",
                    (point.raw_message_id, batch.batch_id, point.event_time.isoformat(),
                     point.model_dump_json()),
                )
                accepted += cursor.rowcount
        return accepted

    def pending(self, limit: int = 100) -> list[TelemetryBatch]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT batch_id, payload FROM telemetry_spool WHERE acked=0 "
                "ORDER BY event_time, batch_id LIMIT ?", (limit,)
            ).fetchall()
        grouped: dict[str, list] = {}
        for batch_id, payload in rows:
            grouped.setdefault(batch_id, []).append(payload)
        return [TelemetryBatch(batch_id=batch_id,
                               points=[_point_from_json(payload) for payload in payloads])
                for batch_id, payloads in grouped.items()]

    def ack(self, batch_id: str) -> int:
        """Mark a sent batch as delivered and return its point count."""
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE telemetry_spool SET acked=1 WHERE batch_id=? AND acked=0", (batch_id,)
            )
            return cursor.rowcount

    def pending_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM telemetry_spool WHERE acked=0"
            ).fetchone()
        return int(row[0])

    def record_alerts(self, alerts: list[TelemetryAlert]) -> int:
        stored = 0
        with self._connect() as connection:
            for alert in alerts:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO telemetry_alerts "
                    "(alert_id, payload, acknowledged, created_at) VALUES (?, ?, ?, ?)",
                    (alert.alert_id, alert.model_dump_json(), int(alert.acknowledged),
                     (alert.created_at or datetime.now(UTC)).isoformat()),
                )
                stored += cursor.rowcount
        return stored

    def alerts(self, limit: int = 100, unacknowledged_only: bool = False) -> list[TelemetryAlert]:
        if limit < 1:
            raise ValueError("limit must be positive")
        where = " WHERE acknowledged=0" if unacknowledged_only else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload, acknowledged FROM telemetry_alerts{where} "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [TelemetryAlert.model_validate_json(row[0]).model_copy(
            update={"acknowledged": bool(row[1])}
        ) for row in rows]

    def ack_alert(self, alert_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE telemetry_alerts SET acknowledged=1 WHERE alert_id=? AND acknowledged=0",
                (alert_id,),
            )
        return cursor.rowcount > 0

    def heartbeat(self, gateway_id: str, connected: bool) -> dict:
        return {
            "gateway_id": gateway_id,
            "connected": connected,
            "pending_points": self.pending_count(),
            "reported_at": datetime.now(UTC).isoformat(),
            "control_mode": "disabled",
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


def _point_from_json(payload: str):
    from packages.contracts.telemetry import TelemetryPoint

    return TelemetryPoint.model_validate_json(payload)
