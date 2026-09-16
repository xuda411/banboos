import json
import os
import sqlite3

from packages.application.legacy_migration import migrate_legacy_snapshot
from packages.application.legacy_snapshot import snapshot_legacy_database
from packages.infrastructure.database_fields import PRICE_FIELDS


def make_source(path):
    fields = ",".join(f"{name} REAL" for name in PRICE_FIELDS)
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE price_data (id INTEGER PRIMARY KEY, node_id INTEGER, run_date TEXT, publish_type TEXT, case_type TEXT, {fields}, source_file TEXT)")
        complete = [1, 7, "2026-01-01", "历史", "实时", *range(96), "a.csv"]
        incomplete = [2, 7, "2026-01-02", "历史", "OK", *([None] + list(range(95))), "b.csv"]
        connection.execute(f"INSERT INTO price_data VALUES ({','.join('?' for _ in complete)})", complete)
        connection.execute(f"INSERT INTO price_data VALUES ({','.join('?' for _ in incomplete)})", incomplete)


def test_migration_preserves_raw_quality_and_canonical_layers(tmp_path):
    source = tmp_path / "legacy.db"
    make_source(source)
    manifest = snapshot_legacy_database(source, tmp_path / "snapshots")
    target = tmp_path / "staging.sqlite3"
    result = migrate_legacy_snapshot(manifest, target)
    assert result["status"] == "succeeded"
    assert result["raw"] == 2
    assert result["quality"] == 2
    assert result["canonical"] == 1
    assert result["rejected"] == 1
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_price_records").fetchone()[0] == 2
        assert connection.execute("SELECT quality_status FROM quality_price_records WHERE source_row_id=2").fetchone()[0] == "rejected"
        assert connection.execute("SELECT market FROM canonical_price_curves").fetchone()[0] == "实时"
        assert connection.execute("SELECT status FROM migration_batches").fetchone()[0] == "succeeded"


def test_migration_rejects_tampered_snapshot(tmp_path):
    source = tmp_path / "legacy.db"
    make_source(source)
    manifest = snapshot_legacy_database(source, tmp_path / "snapshots")
    snapshot = json.loads(manifest.read_text(encoding="utf-8"))["snapshot_path"]
    os.chmod(snapshot, 0o666)
    with open(snapshot, "ab") as stream:
        stream.write(b"tampered")
    try:
        migrate_legacy_snapshot(manifest, tmp_path / "staging.sqlite3")
    except ValueError as error:
        assert "SHA-256" in str(error)
    else:
        raise AssertionError("tampered snapshot must be rejected")
