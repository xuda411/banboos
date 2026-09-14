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
