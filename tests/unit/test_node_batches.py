import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from packages.application.legacy_snapshot import snapshot_legacy_database
from packages.infrastructure.database_fields import PRICE_FIELDS
from packages.infrastructure.legacy_sqlite import LegacySQLiteReader
from packages.infrastructure.staging_sqlite import StagingSQLiteReader
from scripts.migrate_node_batches import choose_scopes, run_batches


def test_choose_scopes_prefers_high_coverage_nodes(tmp_path):
    source = tmp_path / "source.db"
    fields = ",".join(f"{field} REAL" for field in PRICE_FIELDS)
    with sqlite3.connect(source) as connection:
        connection.execute(f"CREATE TABLE price_data (id INTEGER PRIMARY KEY,node_id INTEGER,run_date TEXT,publish_type TEXT,case_type TEXT,{fields},source_file TEXT)")
        values = [0, 1, "2026-01-01", "历史", "实时", *range(96), "x.csv"]
        connection.execute(f"INSERT INTO price_data VALUES ({','.join('?' for _ in values)})", values)
        values[0:5] = [1, 2, "2026-01-01", "历史", "日前"]
        connection.execute(f"INSERT INTO price_data VALUES ({','.join('?' for _ in values)})", values)
        values[0:5] = [2, 2, "2026-01-02", "历史", "日前"]
        connection.execute(f"INSERT INTO price_data VALUES ({','.join('?' for _ in values)})", values)
    manifest = snapshot_legacy_database(source, tmp_path / "snapshots")
    snapshot = Path(json.loads(manifest.read_text(encoding="utf-8"))["snapshot_path"])
    assert choose_scopes(snapshot, 1, None) == [(2, "日前")]
    assert json.loads(manifest.read_text(encoding="utf-8"))["sqlite_integrity_check"] == "ok"
    assert choose_scopes(snapshot, 2, None) == [(2, "日前"), (1, "实时")]
    with pytest.raises(ValueError):
        choose_scopes(snapshot, 2, "OK")
    target, report = tmp_path / "staging.db", tmp_path / "report.json"
    result = run_batches(manifest, target, report, limit=2, max_records=1)
    assert result["status"] == "difference"
    assert [item["status"] for item in result["scopes"]] == ["failed", "matched"]
    assert json.loads(report.read_text(encoding="utf-8")) == result
    retried = run_batches(manifest, target, report, limit=2, max_records=5)
    assert retried["status"] == "matched"
    assert retried["scopes"][1]["migration"]["reused"]
    for protected in (source, snapshot, manifest, target):
        with pytest.raises(ValueError, match="报告不能覆盖"):
            run_batches(manifest, target, protected)


def test_summary_counts_dates_while_quality_preserves_multiple_sources(tmp_path):
    from tests.unit.test_legacy_reader import make_fixture

    source = tmp_path / "source.db"
    make_fixture(source)
    with sqlite3.connect(source) as connection:
        fields = ",".join(PRICE_FIELDS)
        connection.execute(f"INSERT INTO price_data SELECT 2,node_id,run_date,publish_type,case_type,{fields},'other.csv' FROM price_data WHERE id=1")
    manifest = snapshot_legacy_database(source, tmp_path / "snapshots")
    target = tmp_path / "staging.db"
    assert run_batches(manifest, target, tmp_path / "report.json")["status"] == "matched"
    for reader in (LegacySQLiteReader(source), StagingSQLiteReader(target)):
        summary = reader.price_summary(1, "实时", date(2026, 1, 1), date(2026, 1, 1))
        assert summary["valid_days"] == 1
        assert summary["data_points"] == 96
        quality = reader.quality_summary(1, "实时", date(2026, 1, 1), date(2026, 1, 1))
        assert quality["complete_records"] == 2
