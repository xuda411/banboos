from apps.worker.main import run_once
from packages.application.readonly_service import ReadonlyService
from packages.application.run_registry import RunRegistry


def test_price_summary_worker_returns_traceable_result():
    registry = RunRegistry()
    item = registry.submit("price-summary", parameters={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert run_once(registry, ReadonlyService())
    result = registry.get(item.run_id)
    assert result.status == "succeeded"
    assert result.result["node_id"] == 1
    assert result.result["source_mode"] == "demo"
