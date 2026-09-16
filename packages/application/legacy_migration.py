"""Offline, repeatable migration from a verified 1.6.6 snapshot.

The target is a separate SQLite staging database so this first migration step
works without PostgreSQL while preserving the Raw/Quality/Canonical boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from packages.infrastructure.database_fields import PRICE_FIELDS

SCHEMA = """
CREATE TABLE IF NOT EXISTS migration_batches (
 batch_id TEXT PRIMARY KEY, snapshot_sha256 TEXT NOT NULL, source_path TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 raw_count INTEGER NOT NULL DEFAULT 0, quality_count INTEGER NOT NULL DEFAULT 0,
 canonical_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0,
 error_message TEXT
);
CREATE TABLE IF NOT EXISTS raw_price_records (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT, publish_type TEXT, source_file TEXT,
 prices_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 PRIMARY KEY (batch_id, source_row_id)
);
CREATE TABLE IF NOT EXISTS quality_price_records (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT, missing_cells INTEGER NOT NULL,
 non_finite_cells INTEGER NOT NULL, is_complete INTEGER NOT NULL,
 quality_status TEXT NOT NULL, PRIMARY KEY (batch_id, source_row_id)
);
CREATE TABLE IF NOT EXISTS canonical_price_curves (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT NOT NULL, prices_json TEXT NOT NULL,
 source_file TEXT, PRIMARY KEY (node_id, run_date, market)
);
"""


def migrate_legacy_snapshot(manifest_path: str | Path, target_path: str | Path) -> dict:
    manifest_file = Path(manifest_path).expanduser().resolve()
    if not manifest_file.is_file():
        raise ValueError(f"迁移清单不存在：{manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    source = Path(manifest["snapshot_path"]).expanduser().resolve()
    if not source.is_file() or _sha256(source) != manifest.get("sha256"):
        raise ValueError("快照 SHA-256 不匹配，拒绝迁移")
    target = Path(target_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    batch_id = str(uuid4())
    started = datetime.now(UTC).isoformat()
    counters = {"raw": 0, "quality": 0, "canonical": 0, "rejected": 0}
    target_connection = sqlite3.connect(target)
    try:
        target_connection.executescript(SCHEMA)
        target_connection.execute(
            "INSERT INTO migration_batches(batch_id,snapshot_sha256,source_path,started_at,status) VALUES (?,?,?,?,?)",
            (batch_id, manifest["sha256"], str(source), started, "running"),
        )
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as source_connection:
            source_connection.row_factory = sqlite3.Row
            columns = ",".join(["id", "node_id", "run_date", "publish_type", "case_type", *PRICE_FIELDS, "source_file"])
            cursor = source_connection.execute(f"SELECT {columns} FROM price_data ORDER BY id")
            raw_sql = "INSERT INTO raw_price_records VALUES (?,?,?,?,?,?,?,?,?)"
            quality_sql = "INSERT INTO quality_price_records VALUES (?,?,?,?,?,?,?,?,?)"
            canonical_sql = "INSERT OR IGNORE INTO canonical_price_curves VALUES (?,?,?,?,?,?,?)"
            while rows := cursor.fetchmany(1000):
                for row in rows:
                    values = [row[field] for field in PRICE_FIELDS]
                    market = row["case_type"] if row["case_type"] in {"日前", "实时"} else None
                    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
                    digest = hashlib.sha256(payload.encode()).hexdigest()
                    target_connection.execute(raw_sql, (batch_id, row["id"], row["node_id"], row["run_date"], market,
                        row["publish_type"], row["source_file"], payload, digest))
                    counters["raw"] += 1
                    missing = sum(value is None for value in values)
                    non_finite = sum(not _finite(value) for value in values if value is not None)
                    complete = int(market is not None and len(values) == 96 and missing == 0 and non_finite == 0)
                    target_connection.execute(quality_sql, (batch_id, row["id"], row["node_id"], row["run_date"], market,
                        missing, non_finite, complete, "complete" if complete else "rejected"))
                    counters["quality"] += 1
                    if complete:
                        target_connection.execute(canonical_sql, (batch_id, row["id"], row["node_id"], row["run_date"], market, payload, row["source_file"]))
                        counters["canonical"] += target_connection.execute("SELECT changes()").fetchone()[0]
                    else:
                        counters["rejected"] += 1
                target_connection.commit()
        target_connection.execute(
            "UPDATE migration_batches SET finished_at=?,status='succeeded',raw_count=?,quality_count=?,canonical_count=?,rejected_count=? WHERE batch_id=?",
            (datetime.now(UTC).isoformat(), counters["raw"], counters["quality"], counters["canonical"], counters["rejected"], batch_id),
        )
        target_connection.commit()
        return {"batch_id": batch_id, "status": "succeeded", **counters, "target_path": str(target)}
    except Exception as error:
        target_connection.rollback()
        target_connection.execute(
            "UPDATE migration_batches SET finished_at=?,status='failed',error_message=? WHERE batch_id=?",
            (datetime.now(UTC).isoformat(), str(error), batch_id),
        )
        target_connection.commit()
        raise
    finally:
        target_connection.close()


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
