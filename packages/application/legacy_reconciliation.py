"""Reconcile a migrated Canonical layer with its verified legacy snapshot."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from packages.application.legacy_migration import _finite, _sha256
from packages.infrastructure.database_fields import PRICE_FIELDS


def reconcile_legacy_migration(manifest_path: str | Path, target_path: str | Path) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    source = Path(manifest["snapshot_path"]).resolve()
    if not source.is_file() or _sha256(source) != manifest.get("sha256"):
        raise ValueError("快照 SHA-256 不匹配，拒绝对账")
    target = Path(target_path).resolve()
    if not target.is_file():
        raise ValueError(f"迁移目标不存在：{target}")
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as source_db:
        source_db.row_factory = sqlite3.Row
        fields = ",".join(["id", "node_id", "run_date", "case_type", *PRICE_FIELDS])
        expected = 0
        source_min = source_max = None
        for row in source_db.execute(f"SELECT {fields} FROM price_data ORDER BY id"):
            values = [row[field] for field in PRICE_FIELDS]
            if row["case_type"] not in {"日前", "实时"} or not all(_finite(value) for value in values):
                continue
            expected += 1
            day = str(row["run_date"])[:10]
            source_min = day if source_min is None else min(source_min, day)
            source_max = day if source_max is None else max(source_max, day)
    with sqlite3.connect(target) as target_db:
        actual = int(target_db.execute("SELECT COUNT(*) FROM canonical_price_curves").fetchone()[0])
        duplicate_keys = int(target_db.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT node_id || '|' || run_date || '|' || market) "
            "FROM canonical_price_curves"
        ).fetchone()[0])
        target_min, target_max = target_db.execute(
            "SELECT MIN(run_date), MAX(run_date) FROM canonical_price_curves"
        ).fetchone()
        batches = int(target_db.execute(
            "SELECT COUNT(*) FROM migration_batches WHERE status='succeeded'"
        ).fetchone()[0])
    return {"status": "matched" if actual == expected and duplicate_keys == 0 else "difference",
            "source_complete_records": expected, "canonical_records": actual,
            "difference": actual - expected, "duplicate_keys": duplicate_keys,
            "source_first_date": source_min, "source_last_date": source_max,
            "canonical_first_date": target_min, "canonical_last_date": target_max,
            "succeeded_batches": batches, "snapshot_sha256": manifest["sha256"]}
