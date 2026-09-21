from datetime import date

from packages.application.readonly_service import ReadonlyService
from tests.unit.test_legacy_reader import make_fixture


def test_operations_report_groups_provinces_and_months(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    report = ReadonlyService(str(db)).operations_report("实时", date(2026, 1, 1), date(2026, 1, 1))
    assert report.node_count == 1
    assert report.valid_nodes == 1
    assert report.total_valid_days == 1
    assert report.provinces[0].valid_days == 1
    assert report.monthly[0].period == "2026-01"
