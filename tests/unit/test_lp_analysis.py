from apps.worker.main import run_once
from packages.application.readonly_service import ReadonlyService
from packages.application.report_export import export_task_xlsx
from packages.application.run_registry import RunRegistry
from packages.domain.lp_reconciliation import reconcile_lp
from tests.unit.test_legacy_reader import make_fixture


def test_lp_analysis_preserves_trajectory_and_aggregates(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    registry = RunRegistry()
    item = registry.submit("lp-analysis", parameters={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "power_mw": 100, "capacity_mwh": 200,
    })
    assert run_once(registry, ReadonlyService(str(db)))
    completed = registry.get(item.run_id)
    assert completed.status == "succeeded"
    result = completed.result
    assert result["valid_days"] == 1
    day = result["days"][0]
    assert len(day["prices_yuan_per_mwh"]) == 96
    assert len(day["charge_mw"]) == len(day["discharge_mw"]) == len(day["soc"]) == 96
    assert result["monthly"][0]["days"] == 1
    assert result["monthly"][0]["month"] == "2026-01"
    assert result["annual"][0]["days"] == 1
    assert result["annual"][0]["revenue_total_yuan"] == round(result["total_net_revenue_yuan"], 2)
    assert result["comparison"][0]["lp_revenue_yuan"] == day["net_revenue_yuan"]
    assert len(export_task_xlsx(completed)) > 1000
    report = reconcile_lp(result)
    assert report["status"] == "passed"
    assert all(check["status"] == "passed" for check in report["checks"])


def test_lp_analysis_optional_sensitivity_is_bounded(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    registry = RunRegistry()
    item = registry.submit("lp-analysis", parameters={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "power_mw": 100, "capacity_mwh": 200, "include_comparison": False,
        "include_sensitivity": True, "c_rates": [0.5],
    })
    assert run_once(registry, ReadonlyService(str(db)))
    completed = registry.get(item.run_id)
    assert completed.status == "succeeded"
    assert completed.result["comparison"] == []
    assert len(completed.result["sensitivity"]) == 1
