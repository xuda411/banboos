from datetime import UTC, datetime, timedelta

from apps.worker.main import run_once
from packages.application.run_registry import RunRegistry


def test_worker_completes_noop_and_rejects_unknown_kind():
    registry = RunRegistry()
    noop = registry.submit("noop")
    assert run_once(registry)
    assert registry.get(noop.run_id).status == "succeeded"

    unsupported = registry.submit("finance-analysis")
    assert run_once(registry)
    result = registry.get(unsupported.run_id)
    assert result.status == "failed"
    assert result.error_code == "EXECUTOR_NOT_IMPLEMENTED"


def test_cancel_prevents_queued_task_from_running():
    registry = RunRegistry()
    item = registry.submit("noop")
    assert registry.cancel(item.run_id).status == "cancelled"
    assert not run_once(registry)


def test_worker_restart_requeues_running_task():
    registry = RunRegistry()
    item = registry.submit("noop")
    assert registry.claim_next(timeout=0).status == "running"
    assert registry.recover_running() == 1
    assert registry.get(item.run_id).status == "queued"
    assert run_once(registry)
    assert registry.get(item.run_id).status == "succeeded"


def test_stale_queue_item_is_marked_failed_before_audit_listing():
    registry = RunRegistry()
    item = registry.submit("noop")
    stale = registry.get(item.run_id).model_copy(
        update={"created_at": datetime.now(UTC) - timedelta(hours=2)}
    )
    registry._store.save(stale)

    rows = registry.list(limit=10)

    assert rows[0].status == "failed"
    assert rows[0].error_code == "STALE_RUN"
    assert registry.status_counts()["queued"] == 0
