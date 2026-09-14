from packages.application.run_registry import RunRegistry
from packages.application.sqlite_runtime import SQLiteRuntime


def test_sqlite_runtime_shares_queue_and_state_between_registries(tmp_path):
    path = tmp_path / "runtime.sqlite"
    api = SQLiteRuntime(path)
    worker = SQLiteRuntime(path)
    api_registry = RunRegistry(queue=api, store=api)
    worker_registry = RunRegistry(queue=worker, store=worker)

    submitted = api_registry.submit("noop", idempotency_key="manual-check")
    claimed = worker_registry.claim_next(timeout=0)
    assert claimed and claimed.run_id == submitted.run_id
    worker_registry.complete(submitted.run_id, "完成")
    assert api_registry.get(submitted.run_id).status == "succeeded"
    assert api_registry.submit("noop", idempotency_key="manual-check").run_id == submitted.run_id
