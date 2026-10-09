"""Atomic, bounded migration of a verified legacy snapshot into staging v2."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from packages.infrastructure.database_fields import PRICE_FIELDS

SCHEMA = """
CREATE TABLE migration_batches (
 batch_id TEXT PRIMARY KEY, snapshot_sha256 TEXT NOT NULL, source_path TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 raw_count INTEGER NOT NULL DEFAULT 0, quality_count INTEGER NOT NULL DEFAULT 0,
 canonical_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0,
 error_message TEXT
);
CREATE TABLE staging_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE migration_scopes (batch_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL);
CREATE TABLE staging_nodes (id INTEGER PRIMARY KEY, node_name TEXT NOT NULL, province TEXT);
CREATE TABLE raw_price_records (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL UNIQUE, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT, publish_type TEXT, source_file TEXT,
 prices_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 PRIMARY KEY (batch_id, source_row_id)
);
CREATE INDEX raw_scope ON raw_price_records(node_id, market, run_date);
CREATE TABLE quality_price_records (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL UNIQUE, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT, missing_cells INTEGER NOT NULL,
 non_finite_cells INTEGER NOT NULL, is_complete INTEGER NOT NULL,
 quality_status TEXT NOT NULL, PRIMARY KEY (batch_id, source_row_id)
);
CREATE INDEX quality_scope ON quality_price_records(node_id, market, run_date);
CREATE TABLE IF NOT EXISTS price_conflicts (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT, conflict_type TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL, source_file TEXT, canonical_source_row_id INTEGER,
 selection_rule TEXT NOT NULL, processing_state TEXT NOT NULL,
 PRIMARY KEY (batch_id, source_row_id)
);
CREATE INDEX conflict_scope ON price_conflicts(node_id, market, run_date);
CREATE TABLE canonical_price_curves (
 batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
 run_date TEXT NOT NULL, market TEXT NOT NULL, prices_json TEXT NOT NULL,
 source_file TEXT, PRIMARY KEY (node_id, run_date, market)
);
"""


def migration_scope(node_id=None, market=None, start_date=None, end_date=None):
    if market is not None and market not in {"日前", "实时"}:
        raise ValueError("market 必须是 日前 或 实时")
    if node_id is not None and (type(node_id) is not int or node_id <= 0):
        raise ValueError("node_id 必须为正整数")
    for value in (start_date, end_date):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("日期必须为 YYYY-MM-DD")
    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date 不能早于 start_date")
    return dict(node_id=node_id, market=market, start_date=start_date, end_date=end_date)


def scope_query(scope, market_column="case_type"):
    clauses, params = [], []
    for key, column, operator in (("node_id", "node_id", "="), ("market", market_column, "="),
                                  ("start_date", "run_date", ">="), ("end_date", "run_date", "<=")):
        if scope[key] is not None:
            clauses.append(f"{column}{operator}?")
            params.append(scope[key])
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def verified_snapshot(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    source = Path(manifest["snapshot_path"]).resolve()
    if manifest.get("sqlite_integrity_check") != "ok" or not source.is_file() or _sha256(source) != manifest.get("sha256"):
        raise ValueError("快照 SHA-256 或完整性清单不匹配，拒绝读取")
    return manifest, source


def migrate_legacy_snapshot(manifest_path: str | Path, target_path: str | Path,
                            node_id: int | None = None, market: str | None = None,
                            start_date: str | None = None, end_date: str | None = None,
                            max_records: int = 50000) -> dict:
    scope = migration_scope(node_id, market, start_date, end_date)
    scope_json = json.dumps(scope, sort_keys=True, ensure_ascii=False)
    manifest, source = verified_snapshot(manifest_path)
    target = Path(target_path).resolve()
    forbidden = [source, Path(manifest_path).resolve(), Path(manifest["source_path"]).resolve()]
    if target in forbidden or (target.exists() and any(target.samefile(p) for p in forbidden if p.exists())):
        raise ValueError("迁移目标不能覆盖源库、快照或清单")
    # The normal bounded replay workflow uses 50k–500k rows per batch.  A
    # verified full-history delivery import may contain several million rows;
    # allow that explicit one-shot only after the snapshot hash/integrity checks
    # above have passed.  The upper bound still prevents an accidental unbound
    # scan of an arbitrary legacy file.
    if not 1 <= max_records <= 5_000_000:
        raise ValueError("每批上限必须为 1–5000000 条")
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < 1024 ** 3:
        raise ValueError("目标盘可用空间不足 1 GiB，停止迁移")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(target)) as dst:
        src.row_factory = sqlite3.Row
        tables = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables and "staging_meta" not in tables:
            raise ValueError("旧 staging 格式未发布，请使用新的目标文件重新迁移")
        if not tables:
            dst.executescript(SCHEMA)
            dst.executemany("INSERT INTO staging_meta VALUES (?,?)", [("format_version", "2"), ("snapshot_sha256", manifest["sha256"])])
            dst.commit()
        if dict(dst.execute("SELECT key,value FROM staging_meta")) != {"format_version": "2", "snapshot_sha256": manifest["sha256"]}:
            raise ValueError("目标格式或快照不同，不允许混合来源")
        dst.execute("""CREATE TABLE IF NOT EXISTS price_conflicts (
            batch_id TEXT NOT NULL, source_row_id INTEGER NOT NULL, node_id INTEGER NOT NULL,
            run_date TEXT NOT NULL, market TEXT, conflict_type TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL, source_file TEXT, canonical_source_row_id INTEGER,
            selection_rule TEXT NOT NULL, processing_state TEXT NOT NULL,
            PRIMARY KEY (batch_id, source_row_id))""")
        dst.execute("CREATE INDEX IF NOT EXISTS conflict_scope ON price_conflicts(node_id, market, run_date)")
        dst.commit()
        previous = dst.execute("SELECT b.batch_id FROM migration_batches b JOIN migration_scopes s USING(batch_id) WHERE b.status='succeeded' AND s.scope_json=?", (scope_json,)).fetchone()
        if previous:
            return {"batch_id": previous[0], "status": "succeeded", "reused": True, "target_path": str(target)}
        batch_id = str(uuid4())
        dst.execute("INSERT INTO migration_batches(batch_id,snapshot_sha256,source_path,started_at,status) VALUES (?,?,?,?,?)",
                    (batch_id, manifest["sha256"], str(source), datetime.now(UTC).isoformat(), "running"))
        dst.execute("INSERT INTO migration_scopes VALUES (?,?)", (batch_id, scope_json))
        dst.commit()
        counters = dict(raw=0, quality=0, canonical=0, rejected=0)
        try:
            condition, params = scope_query(scope)
            count = src.execute(f"SELECT COUNT(*) FROM price_data{condition}", params).fetchone()[0]
            if count > max_records:
                raise ValueError(f"本批 {count} 条超过上限 {max_records}，请缩小节点或日期范围")
            dst.execute("BEGIN IMMEDIATE")
            if src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nodes'").fetchone():
                dst.executemany("INSERT OR IGNORE INTO staging_nodes VALUES (?,?,?)",
                                src.execute("SELECT id,node_name,province FROM nodes"))
            columns = ",".join(["id", "node_id", "run_date", "publish_type", "case_type", *PRICE_FIELDS, "source_file"])
            cursor = src.execute(f"SELECT {columns} FROM price_data{condition} ORDER BY id", params)
            for offset, row in enumerate(cursor):
                if offset % 1000 == 0 and shutil.disk_usage(target.parent).free < 1024 ** 3:
                    raise ValueError("可用空间低于 1 GiB，当前批次回滚")
                if dst.execute("SELECT 1 FROM raw_price_records WHERE source_row_id=?", (row["id"],)).fetchone():
                    continue
                values = [row[f] for f in PRICE_FIELDS]
                payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
                dst.execute("INSERT INTO raw_price_records VALUES (?,?,?,?,?,?,?,?,?)", (batch_id, row["id"], row["node_id"], row["run_date"], row["case_type"], row["publish_type"], row["source_file"], payload, hashlib.sha256(payload.encode()).hexdigest()))
                counters["raw"] += 1
                missing = sum(v is None for v in values)
                non_finite = sum(not _finite(v) for v in values if v is not None)
                try:
                    valid_date = date.fromisoformat(row["run_date"]).isoformat() == row["run_date"]
                except (ValueError, TypeError):
                    valid_date = False
                complete = int(valid_date and row["case_type"] in {"日前", "实时"} and not missing and not non_finite)
                status = "complete" if complete else "rejected"
                if complete:
                    normalized = json.dumps([float(v) for v in values], separators=(",", ":"))
                    key = (row["node_id"], row["run_date"], row["case_type"])
                    old = dst.execute("SELECT source_row_id,prices_json FROM canonical_price_curves WHERE node_id=? AND run_date=? AND market=?", key).fetchone()
                    conflict_type = None
                    selection_rule = "single_valid_source"
                    processing_state = "resolved"
                    if old:
                        status = "duplicate" if old[1] == normalized else "multiple_source"
                        conflict_type = status
                        selection_rule = "lowest_source_id_duplicate" if status == "duplicate" else "lowest_source_id_provisional"
                        processing_state = "manual_review_required" if status == "multiple_source" else "resolved"
                    # Curves/dispatch retain the lowest valid source id, like desktop.
                    # Annual baselines separately retain ALL raw candidates.
                    if not old or row["id"] < old[0]:
                        dst.execute("INSERT OR REPLACE INTO canonical_price_curves VALUES (?,?,?,?,?,?,?)", (batch_id, row["id"], *key, normalized, row["source_file"]))
                        counters["canonical"] += int(old is None)
                else:
                    counters["rejected"] += 1
                    old = dst.execute("SELECT source_row_id FROM canonical_price_curves WHERE node_id=? AND run_date=? AND market=?", (row["node_id"], row["run_date"], row["case_type"])).fetchone()
                    conflict_type = "rejected" if old else "no_canonical"
                    selection_rule = "candidate_rejected_canonical_retained" if old else "no_valid_canonical_candidate"
                    processing_state = "manual_review_required"
                if conflict_type:
                    dst.execute("INSERT OR REPLACE INTO price_conflicts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (batch_id, row["id"], row["node_id"], row["run_date"], row["case_type"],
                                 conflict_type, hashlib.sha256(payload.encode()).hexdigest(), row["source_file"],
                                 old[0] if old else None, selection_rule, processing_state))
                dst.execute("INSERT INTO quality_price_records VALUES (?,?,?,?,?,?,?,?,?)", (batch_id, row["id"], row["node_id"], row["run_date"], row["case_type"], missing, non_finite, complete, status))
                counters["quality"] += 1
            dst.execute("UPDATE migration_batches SET finished_at=?,status='succeeded',raw_count=?,quality_count=?,canonical_count=?,rejected_count=? WHERE batch_id=?", (datetime.now(UTC).isoformat(), *counters.values(), batch_id))
            dst.commit()
        except BaseException as error:
            dst.rollback()
            dst.execute("UPDATE migration_batches SET finished_at=?,status='failed',error_message=? WHERE batch_id=?", (datetime.now(UTC).isoformat(), str(error) or type(error).__name__, batch_id))
            dst.commit()
            raise
    return {"batch_id": batch_id, "status": "succeeded", **counters, "target_path": str(target), "scope": scope}


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
