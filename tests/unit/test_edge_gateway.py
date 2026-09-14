from datetime import UTC, datetime

from apps.edge.gateway import TelemetrySpool
from apps.edge.simulator import generate_batch
from packages.contracts.telemetry import TelemetryAlert
from packages.domain.telemetry_alerts import evaluate_alerts


def test_spool_deduplicates_replays_and_acknowledges(tmp_path):
    at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    batch = generate_batch(at=at)
    spool = TelemetrySpool(tmp_path / "edge-spool.sqlite")

    assert spool.ingest(batch) == 3
    assert spool.ingest(batch) == 0
    pending = spool.pending()
    assert len(pending) == 1
    assert pending[0].batch_id == batch.batch_id
    assert spool.pending_count() == 3
    assert len(spool.recent(station_id="demo-station", point_id="soc")) == 1
    assert spool.ack(batch.batch_id) == 3
    assert spool.pending_count() == 0


def test_spool_replays_batches_in_event_time_order_and_reports_safe_mode(tmp_path):
    spool = TelemetrySpool(tmp_path / "edge-spool.sqlite")
    later = generate_batch(at=datetime(2026, 1, 2, 3, 5, tzinfo=UTC))
    earlier = generate_batch(at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC))
    spool.ingest(later)
    spool.ingest(earlier)

    pending = spool.pending(limit=2)
    assert [item.points[0].event_time for item in pending] == sorted(
        item.points[0].event_time for item in pending
    )
    heartbeat = spool.heartbeat("gw-01", connected=False)
    assert heartbeat["pending_points"] == 6
    assert heartbeat["control_mode"] == "disabled"


def test_pending_limit_keeps_whole_batches_and_ack_preserves_other_batches(tmp_path):
    path = tmp_path / "edge-spool.sqlite"
    spool = TelemetrySpool(path)
    early = generate_batch(at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC))
    later = generate_batch(at=datetime(2026, 1, 2, 3, 5, tzinfo=UTC))
    spool.ingest(later)
    spool.ingest(early)

    first = spool.pending(limit=1)
    assert len(first) == 1
    assert first[0].batch_id == early.batch_id
    assert {point.raw_message_id for point in first[0].points} == {
        point.raw_message_id for point in early.points
    }
    assert spool.ack(first[0].batch_id) == 3

    reopened = TelemetrySpool(path)
    remaining = reopened.pending(limit=1)
    assert len(remaining) == 1
    assert remaining[0].batch_id == later.batch_id
    assert len(remaining[0].points) == reopened.pending_count() == 3
    assert reopened.ack(early.batch_id) == 0


def test_telemetry_alerts_are_structured_and_do_not_control_devices():
    batch = generate_batch().model_copy(update={"points": [
        generate_batch().points[0].model_copy(update={"value": 106}),
        generate_batch().points[2].model_copy(update={"value": 66}),
    ]})
    alerts = evaluate_alerts(batch)
    assert {alert.code for alert in alerts} == {"SOC_OUT_OF_RANGE", "TEMPERATURE_HIGH"}
    assert all(alert.severity == "critical" for alert in alerts)


def test_alerts_are_persisted_and_can_be_acknowledged(tmp_path):
    spool = TelemetrySpool(tmp_path / "edge-spool.sqlite")
    alert = TelemetryAlert(alert_id="alert-001", batch_id="batch-001", code="SOC_OUT_OF_RANGE",
                           severity="critical", station_id="demo", device_id="pcs",
                           point_id="soc", event_time=datetime.now(UTC), message="SOC 越界")
    assert spool.record_alerts([alert]) == 1
    assert spool.record_alerts([alert]) == 0
    assert spool.alerts(unacknowledged_only=True)[0].alert_id == "alert-001"
    assert spool.ack_alert("alert-001")
    assert spool.alerts(unacknowledged_only=True) == []
