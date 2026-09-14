import sqlite3
from datetime import date

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
