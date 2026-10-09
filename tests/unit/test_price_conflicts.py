import sqlite3
from datetime import date

from packages.application.legacy_migration import migrate_legacy_snapshot
from packages.application.legacy_snapshot import snapshot_legacy_database
from packages.infrastructure.database_fields import PRICE_FIELDS
from packages.infrastructure.staging_sqlite import StagingSQLiteReader


def test_conflict_categories_are_isolated_and_traceable(tmp_path):
    source = tmp_path / "source.db"
    fields = ",".join(f"{name} REAL" for name in PRICE_FIELDS)
    with sqlite3.connect(source) as db:
        db.execute(f"CREATE TABLE price_data (id INTEGER PRIMARY KEY,node_id INTEGER,run_date TEXT,publish_type TEXT,case_type TEXT,{fields},source_file TEXT)")
        base = [1, 7, "2026-01-01", "历史", "实时", *range(96), "a.csv"]
        same = [2, 7, "2026-01-01", "历史", "实时", *range(96), "b.csv"]
        different = [3, 7, "2026-01-01", "历史", "实时", *([999] + list(range(1, 96))), "c.csv"]
        rejected = [4, 7, "2026-01-02", "历史", "实时", *([None] + list(range(95))), "bad.csv"]
        rejected_with_canonical = [5, 7, "2026-01-01", "历史", "实时", *([None] + list(range(95))), "bad-same-day.csv"]
        for row in (base, same, different, rejected, rejected_with_canonical):
            db.execute(f"INSERT INTO price_data VALUES ({','.join('?' for _ in row)})", row)
    manifest = snapshot_legacy_database(source, tmp_path / "snapshots")
    target = tmp_path / "staging.db"
    migrate_legacy_snapshot(manifest, target)
    with sqlite3.connect(target) as db:
        rows = db.execute("SELECT source_row_id, conflict_type, canonical_source_row_id, selection_rule, processing_state, payload_sha256 FROM price_conflicts ORDER BY source_row_id").fetchall()
        assert [row[1] for row in rows] == ["duplicate", "multiple_source", "no_canonical", "rejected"]
        assert rows[0][2] == 1 and rows[1][2] == 1
        assert rows[1][3] == "lowest_source_id_provisional"
        assert rows[1][4] == "manual_review_required"
        assert all(len(row[5]) == 64 for row in rows)
        assert db.execute("SELECT quality_status FROM quality_price_records WHERE source_row_id=4").fetchone()[0] == "rejected"
    reader = StagingSQLiteReader(target)
    quality = reader.quality_summary(7, "实时", date(2026, 1, 1), date(2026, 1, 2))
    assert quality["duplicate_records"] == 1
    assert quality["multiple_source_records"] == 1
    assert quality["rejected_records"] == 1
    assert quality["no_canonical_records"] == 1
    assert quality["manual_review_records"] == 3
    summary = reader.price_summary(7, "实时", date(2026, 1, 1), date(2026, 1, 2))
    assert summary["valid_days"] == 1
    assert summary["data_status"] == "manual_review_required"
