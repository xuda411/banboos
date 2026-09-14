from datetime import UTC, datetime

import pytest

from apps.edge.gateway import TelemetrySpool
from apps.edge.simulator import generate_batch
from packages.application.operations_service import OperationsService, OperationsUnavailable
from packages.application.readonly_service import ReadonlyService
from packages.application.run_registry import RedisStateStore, RunRegistry
from packages.application.sqlite_runtime import SQLiteRuntime
from packages.contracts.telemetry import TelemetryAlert


@pytest.mark.parametrize("storage", ["memory", "sqlite"])
def test_summary_counts_all_tasks_telemetry_and_alerts(tmp_path, storage):
    runtime = SQLiteRuntime(tmp_path / "runtime.sqlite") if storage == "sqlite" else None
    registry = RunRegistry(queue=runtime, store=runtime)
    for _ in range(105):
        registry.submit("readonly-price-analysis")
    succeeded = registry.claim_next(timeout=0)
    registry.complete(succeeded.run_id)
    failed = registry.claim_next(timeout=0)
    registry.fail(failed.run_id, "测试失败")
    cancelled = registry.claim_next(timeout=0)
    registry.cancel(cancelled.run_id)
    registry.claim_next(timeout=0)

    spool = TelemetrySpool(tmp_path / "edge.sqlite")
    early = generate_batch(at=datetime(2026, 1, 1, tzinfo=UTC))
    late = generate_batch(at=datetime(2026, 1, 2, tzinfo=UTC))
    spool.ingest(early)
    spool.ingest(late)
    spool.ingest(late)
    spool.ack(early.batch_id)
    for index, severity in enumerate(["warning", "critical", "critical"]):
        spool.record_alerts([TelemetryAlert(
            alert_id=f"alert-{index}", batch_id=late.batch_id, code="TEST",
            severity=severity, station_id="demo", device_id="pcs", point_id="soc",
            event_time=datetime.now(UTC), message="测试告警",
        )])
    spool.ack_alert("alert-2")

    summary = OperationsService(ReadonlyService(), registry, spool).summary()
    assert summary.task_counts.by_status == {
        "queued": 101, "running": 1, "succeeded": 1, "failed": 1, "cancelled": 1,
    }
    assert summary.task_counts.total == 105
    assert summary.model_dump()["task_counts"]["total"] == 105
    assert summary.telemetry.model_dump() == {
        "total_points": 6, "pending_points": 3, "acknowledged_points": 3, "pending_batches": 1,
    }
    assert summary.alerts.model_dump() == {
        "total": 3, "unacknowledged": 2, "acknowledged": 1,
        "unacknowledged_critical": 1, "unacknowledged_warning": 1,
    }
    assert summary.node_count == 2
    assert summary.data_mode == "demo"
    assert summary.control_mode == "disabled"
    assert summary.collection_started_at <= summary.generated_at


def test_summary_distinguishes_unavailable_storage_from_empty_storage(tmp_path):
    class UnavailableNodes:
        data_mode = "isolated-copy"

        def node_count(self):
            raise RuntimeError("private database path and credentials")

    service = OperationsService(
        UnavailableNodes(), RunRegistry(), TelemetrySpool(tmp_path / "edge.sqlite"),
    )
    with pytest.raises(OperationsUnavailable) as caught:
        service.summary()
    assert caught.value.component == "nodes"
    assert "private" not in str(caught.value)


def test_redis_status_counts_deduplicate_scan_and_bound_reads():
    class FakeRedis:
        def __init__(self):
            self.read_sizes = []

        def scan_iter(self, **kwargs):
            yield from [f"run-{index}" for index in range(260)]
            yield "run-1"  # SCAN can return a key again.
            yield "deleted"

        def mget(self, keys):
            self.read_sizes.append(len(keys))
            return [None if key == "deleted" else '{"status":"queued"}' for key in keys]

    store = RedisStateStore.__new__(RedisStateStore)
    store._client = FakeRedis()
    assert store.status_counts() == {"queued": 260}
    assert max(store._client.read_sizes) <= 128
