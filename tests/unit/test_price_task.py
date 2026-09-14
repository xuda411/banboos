from apps.worker.main import run_once
from packages.application.readonly_service import ReadonlyService
from packages.application.run_registry import RunRegistry
from tests.unit.test_legacy_reader import make_fixture


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


def test_price_analysis_worker_uses_power_capacity_ratio(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    make_fixture(path)
    registry = RunRegistry()
    item = registry.submit("price-analysis", parameters={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "power_mw": 100, "capacity_mwh": 200,
    })
    assert run_once(registry, ReadonlyService(str(path)))
    result = registry.get(item.run_id)
    assert result.status == "succeeded"
    assert result.result["duration_hours"] == 2.0
    assert result.result["valid_days"] == 1
    assert result.result["annualized_revenue_yuan"] > 0
