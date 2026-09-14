import sqlite3
from datetime import date

import pytest

from packages.application.readonly_service import ReadonlyService
from packages.infrastructure.database_fields import PRICE_FIELDS
from packages.infrastructure.legacy_sqlite import LegacySQLiteReader


def make_fixture(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, node_name TEXT, province TEXT)")
    connection.execute("CREATE TABLE price_data (id INTEGER PRIMARY KEY, node_id INTEGER, run_date TEXT, publish_type TEXT, case_type TEXT, "
                       + ",".join(f"{field} REAL" for field in PRICE_FIELDS)
                       + ", source_file TEXT)")
    connection.execute("CREATE TABLE node_meteorology_data (id INTEGER PRIMARY KEY, node_id INTEGER, data_time TEXT, source TEXT, "
                       "ghi REAL, wind_speed_100m REAL, temp REAL, is_outlier INTEGER DEFAULT 0)")
    connection.execute("INSERT INTO nodes VALUES (1, '测试节点', '湖北')")
    values = [1, 1, '2026-01-01', '历史导入', '实时', *range(96), 'fixture.csv']
    connection.execute("INSERT INTO price_data VALUES (" + ",".join("?" for _ in values) + ")", values)
    connection.execute("INSERT INTO node_meteorology_data VALUES (1, 1, '2026-01-01 00:00:00', 'fixture', 500, 6, 25, 0)")
    connection.commit()
    connection.close()


def test_legacy_reader_is_read_only_and_returns_contracts(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    make_fixture(path)
    reader = LegacySQLiteReader(path)

    assert reader.list_nodes() == [{"id": 1, "name": "测试节点", "province": "湖北"}]
    result = reader.price_summary(1, "实时", date(2026, 1, 1), date(2026, 1, 1))
    assert result["valid_days"] == 1
    assert result["data_points"] == 96
    weather = reader.weather_summary(1)
    assert weather["observations"] == 1

    connection = reader._connect()
    try:
        connection.execute("INSERT INTO nodes VALUES (2, 'should fail', '广东')")
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("legacy reader must expose a read-only connection")
    finally:
        connection.close()


def test_quality_summary_counts_incomplete_cells(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    make_fixture(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE price_data SET p0015=NULL WHERE node_id=1")
        connection.commit()
    summary = LegacySQLiteReader(path).quality_summary(1, "实时", date(2026, 1, 1), date(2026, 1, 2))
    assert summary["total_records"] == 1
    assert summary["complete_records"] == 0
    assert summary["missing_cells"] == 1
    assert summary["coverage_ratio"] == 0


def test_readonly_service_exposes_complete_daily_curves(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    make_fixture(path)
    curves = ReadonlyService(path).curves(1, "实时", date(2026, 1, 1), date(2026, 1, 2))
    assert len(curves) == 1
    assert curves[0].run_date == date(2026, 1, 1)
    assert len(curves[0].prices) == 96
    assert curves[0].prices[0] == 0


def test_readonly_service_exposes_weather_and_estimated_power(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    make_fixture(path)
    series = ReadonlyService(path).weather_series(1)
    assert len(series) == 1
    assert series[0].ghi_w_m2 == 500
    assert series[0].pv_predict_power_mw == pytest.approx(49.0)
    assert series[0].wind_predict_power_mw == pytest.approx(11.1111, rel=1e-3)
    assert series[0].is_power_simulated is True
