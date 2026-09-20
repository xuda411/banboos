from apps.worker.main import run_once
from packages.application.readonly_service import ReadonlyService
from packages.application.report_export import export_task_xlsx
from packages.application.run_registry import RunRegistry
from packages.domain.investment_scenario import build_investment_scenario
from tests.unit.test_legacy_reader import make_fixture


def _baseline():
    return {
        "average_daily_revenue_yuan": 10000,
        "snapshot_id": "snap-1", "node_id": 7, "market": "实时",
        "start_date": "2025-01-01", "end_date": "2025-12-31",
        "power_mw": 100, "capacity_mwh": 200, "duration_hours": 2,
        "spread_yuan_per_mwh": 80,
    }


def test_scenario_applies_controls_once_and_keeps_traceability():
    result = build_investment_scenario(_baseline(), {
        "source_run_id": "source-run-12345678901234567890123456789012",
        "scenario_name": "保守情景", "annual_cycles": 300,
        "utilization": 0.8, "spread_factor": 0.9, "retention_rate": 0.95,
    }, "scenario-run-12345678901234567890123456789012")

    assert result["annual_revenue_yuan"] == 2_052_000
    assert result["annualized_revenue_yuan"] == result["annual_revenue_yuan"]
    assert result["source_run_id"].startswith("source-run")
    assert result["financial_parameters"]["source_run_id"].startswith("scenario-run")


def test_scenario_clamps_negative_baseline_revenue_to_zero():
    baseline = _baseline()
    baseline["average_daily_revenue_yuan"] = -1
    result = build_investment_scenario(baseline, {
        "source_run_id": "source-run-12345678901234567890123456789012",
        "scenario_name": "基准情景", "annual_cycles": 350,
        "utilization": 1, "spread_factor": 1, "retention_rate": 1,
    }, "scenario-run-12345678901234567890123456789012")
    assert result["annual_revenue_yuan"] == 0


def test_worker_builds_scenario_from_price_analysis_and_exports(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    registry = RunRegistry()
    source = registry.submit("price-analysis", parameters={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "power_mw": 100, "capacity_mwh": 200, "round_trip_efficiency": 0.92,
    })
    assert run_once(registry, ReadonlyService(str(db)))
    assert registry.get(source.run_id).status == "succeeded"
    scenario = registry.submit("investment-scenario", parameters={
        "source_run_id": source.run_id, "scenario_name": "测试情景", "spread_factor": 0.8,
        "annual_cycles": 300, "utilization": 0.9, "retention_rate": 0.95,
    })
    assert run_once(registry)
    completed = registry.get(scenario.run_id)
    assert completed.status == "succeeded"
    assert completed.result["annualized_revenue_yuan"] == completed.result["annual_revenue_yuan"]
    assert len(export_task_xlsx(completed)) > 1000
