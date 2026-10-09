"""Create an auditable, de-duplicated derivative of a 1.6.6 SQLite snapshot.

The legacy source is opened read-only.  The derivative keeps the original
legacy schema so it can be used by the desktop-compatible readers, while
recording every removed source row and every node-name matching decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import unicodedata
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = unicodedata.normalize("NFKC", text).strip()
    return " ".join(text.split())


def _complete(row: sqlite3.Row, price_fields: tuple[str, ...]) -> bool:
    for field in price_fields:
        value = row[field]
        if value is None:
            return False
        try:
            if not math.isfinite(float(value)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _payload_hash(row: sqlite3.Row, price_fields: tuple[str, ...]) -> str:
    payload = json.dumps(
        [row[field] for field in price_fields],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _copy_snapshot(source: Path, target_tmp: Path) -> None:
    source_uri = source.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as src, closing(sqlite3.connect(target_tmp)) as dst:
        src.backup(dst, pages=8192)
        dst.commit()


def clean_snapshot(source_path: str | Path, target_path: str | Path, report_path: str | Path) -> dict:
    source = Path(source_path).resolve()
    target = Path(target_path).resolve()
    report_file = Path(report_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == target:
        raise ValueError("清洗目标不能覆盖 1.6.6 源库或快照")
    if target.exists():
        raise FileExistsError(f"清洗目标已存在，请先移走或删除工作副本：{target}")
    if shutil.disk_usage(target.parent).free < 8 * 1024**3:
        raise ValueError("目标盘可用空间低于 8 GiB，停止清洗")

    target.parent.mkdir(parents=True, exist_ok=True)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + f".tmp-{os.getpid()}")
    if tmp.exists():
        tmp.unlink()

    source_sha256 = _hash_file(source)
    run_id = str(uuid4())
    duplicate_groups: list[dict] = []
    node_aliases: list[dict] = []
    try:
        _copy_snapshot(source, tmp)
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as src:
            src.row_factory = sqlite3.Row
            price_fields = tuple(
                row["name"]
                for row in src.execute('PRAGMA table_info("price_data")')
                if row["name"].startswith("p") and row["name"][1:].isdigit()
            )
            if len(price_fields) != 96:
                raise ValueError(f"price_data 应有 96 个 15 分钟字段，实际为 {len(price_fields)}")
            integrity = src.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"源快照完整性检查失败：{integrity}")

            nodes = src.execute("SELECT id,node_name,province FROM nodes ORDER BY id").fetchall()
            by_match_key: defaultdict[str, list[int]] = defaultdict(list)
            for node in nodes:
                match_key = f"{_normalise_text(node['province'])}|{_normalise_text(node['node_name'])}"
                by_match_key[match_key].append(int(node["id"]))
                node_aliases.append(
                    {
                        "node_id": int(node["id"]),
                        "node_name": node["node_name"],
                        "province": node["province"],
                        "normalized_name": _normalise_text(node["node_name"]),
                        "normalized_province": _normalise_text(node["province"]),
                        "match_key": match_key,
                    }
                )
            for alias in node_aliases:
                candidates = by_match_key[alias["match_key"]]
                alias["candidate_count"] = len(candidates)
                alias["status"] = "unique" if len(candidates) == 1 else "review_required"
                alias["reason"] = (
                    "省份与节点名规范化后唯一，保留原 node_id"
                    if len(candidates) == 1
                    else "规范化后存在多个 node_id，禁止自动合并"
                )

            duplicate_cursor = src.execute(
                """
                SELECT node_id,run_date,case_type,GROUP_CONCAT(id) AS ids,COUNT(*) AS row_count
                FROM price_data
                WHERE case_type IN ('日前','实时')
                GROUP BY node_id,run_date,case_type
                HAVING COUNT(*) > 1
                ORDER BY node_id,run_date,case_type
                """
            )
            for group in duplicate_cursor:
                ids = [int(value) for value in group["ids"].split(",")]
                rows = [src.execute("SELECT * FROM price_data WHERE id=?", (row_id,)).fetchone() for row_id in ids]
                complete_rows = [row for row in rows if _complete(row, price_fields)]
                # Lowest complete source id is the 1.6.6-compatible stable
                # representative.  All alternatives remain in the source
                # snapshot and are listed in this registry.
                candidates = complete_rows or rows
                chosen = min(candidates, key=lambda row: int(row["id"]))
                duplicate_groups.append(
                    {
                        "node_id": int(group["node_id"]),
                        "run_date": group["run_date"],
                        "market": group["case_type"],
                        "source_ids": ids,
                        "kept_id": int(chosen["id"]),
                        "removed_ids": [int(row["id"]) for row in rows if int(row["id"]) != int(chosen["id"])],
                        "payload_hashes": [_payload_hash(row, price_fields) for row in rows],
                        "publish_types": [row["publish_type"] for row in rows],
                        "source_files": [row["source_file"] for row in rows],
                        "all_complete": len(complete_rows) == len(rows),
                        "same_payload": len({_payload_hash(row, price_fields) for row in rows}) == 1,
                    }
                )

        removed_ids = [row_id for group in duplicate_groups for row_id in group["removed_ids"]]
        removed_set = set(removed_ids)
        with closing(sqlite3.connect(tmp)) as dst:
            dst.row_factory = sqlite3.Row
            dst.execute("PRAGMA foreign_keys=ON")
            dst.executescript(
                """
                CREATE TABLE cleaning_runs (
                    run_id TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, algorithm_version TEXT NOT NULL,
                    source_price_rows INTEGER NOT NULL, cleaned_price_rows INTEGER NOT NULL,
                    duplicate_groups INTEGER NOT NULL, removed_duplicate_rows INTEGER NOT NULL,
                    conflicting_groups INTEGER NOT NULL, normalized_node_collision_groups INTEGER NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE price_duplicate_registry (
                    run_id TEXT NOT NULL, node_id INTEGER NOT NULL, run_date TEXT NOT NULL,
                    market TEXT NOT NULL, kept_id INTEGER NOT NULL, source_ids_json TEXT NOT NULL,
                    removed_ids_json TEXT NOT NULL, payload_hashes_json TEXT NOT NULL,
                    publish_types_json TEXT NOT NULL, source_files_json TEXT NOT NULL,
                    all_complete INTEGER NOT NULL, same_payload INTEGER NOT NULL,
                    decision_reason TEXT NOT NULL,
                    PRIMARY KEY (run_id,node_id,run_date,market)
                );
                CREATE TABLE node_name_aliases (
                    run_id TEXT NOT NULL, node_id INTEGER NOT NULL, node_name TEXT NOT NULL,
                    province TEXT, normalized_name TEXT NOT NULL, normalized_province TEXT NOT NULL,
                    match_key TEXT NOT NULL, candidate_count INTEGER NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL,
                    PRIMARY KEY (run_id,node_id)
                );
                CREATE INDEX idx_price_duplicate_registry_node ON price_duplicate_registry(node_id,run_date,market);
                CREATE INDEX idx_node_name_aliases_key ON node_name_aliases(match_key);
                """
            )
            # Delete only duplicate business-key rows from the derivative.
            # Invalid/incomplete non-duplicate rows stay for quality review.
            dst.executemany("DELETE FROM price_data WHERE id=?", ((row_id,) for row_id in removed_set))
            dst.executemany(
                """
                INSERT INTO price_duplicate_registry
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    (
                        run_id,
                        group["node_id"],
                        group["run_date"],
                        group["market"],
                        group["kept_id"],
                        json.dumps(group["source_ids"], ensure_ascii=False),
                        json.dumps(group["removed_ids"], ensure_ascii=False),
                        json.dumps(group["payload_hashes"], ensure_ascii=False),
                        json.dumps(group["publish_types"], ensure_ascii=False),
                        json.dumps(group["source_files"], ensure_ascii=False),
                        int(group["all_complete"]),
                        int(group["same_payload"]),
                        "保留完整记录中最早 source_id；冲突来源保留在源快照并登记",
                    )
                    for group in duplicate_groups
                ),
            )
            dst.executemany(
                "INSERT INTO node_name_aliases VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    (
                        run_id,
                        alias["node_id"],
                        alias["node_name"],
                        alias["province"],
                        alias["normalized_name"],
                        alias["normalized_province"],
                        alias["match_key"],
                        alias["candidate_count"],
                        alias["status"],
                        alias["reason"],
                    )
                    for alias in node_aliases
                ),
            )
            source_count = dst.execute("SELECT COUNT(*) FROM price_data").fetchone()[0] + len(removed_set)
            cleaned_count = dst.execute("SELECT COUNT(*) FROM price_data").fetchone()[0]
            collision_groups = sum(1 for ids in by_match_key.values() if len(ids) > 1)
            dst.execute(
                """
                INSERT INTO cleaning_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    str(source),
                    source_sha256,
                    datetime.now(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                    "legacy-price-clean-v1",
                    source_count,
                    cleaned_count,
                    len(duplicate_groups),
                    len(removed_set),
                    sum(not group["same_payload"] for group in duplicate_groups),
                    collision_groups,
                    "succeeded",
                ),
            )
            dst.commit()
            integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"清洗副本完整性检查失败：{integrity}")
            foreign_keys = dst.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_keys:
                raise ValueError(f"清洗副本外键检查失败：{len(foreign_keys)} 条")
            dst.execute("VACUUM")

        os.replace(tmp, target)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise

    with closing(sqlite3.connect(target)) as check_db:
        cleaned_price_rows = check_db.execute("SELECT COUNT(*) FROM price_data").fetchone()[0]
    result = {
        "report_version": "legacy-price-clean-delivery-v1",
        "run_id": run_id,
        "source": {"path": str(source), "sha256": source_sha256},
        "target": {"path": str(target), "sha256": _hash_file(target)},
        "before": {
            "node_count": len(node_aliases),
            "price_rows": len(removed_ids) + cleaned_price_rows,
        },
        "after": {
            "node_count": len(node_aliases),
            "price_rows": cleaned_price_rows,
        },
        "duplicates": {
            "groups": len(duplicate_groups),
            "removed_rows": len(removed_ids),
            "conflicting_groups": sum(not group["same_payload"] for group in duplicate_groups),
            "same_payload_groups": sum(group["same_payload"] for group in duplicate_groups),
        },
        "node_matching": {
            "normalized_collision_groups": sum(1 for ids in by_match_key.values() if len(ids) > 1),
            "policy": "省份 + NFKC 规范化节点名；冲突只标记 review_required，不自动合并 node_id",
        },
        "policy": {
            "market_types": ["日前", "实时"],
            "ok_missing": "保留为历史质量/发布标签，不作为市场类型，也不作为删除依据",
            "representative": "每个节点+日期+市场优先保留完整记录中最早 source_id；若均不完整则保留最早 source_id，兼容 1.6.6 选择顺序",
            "source_unchanged": True,
        },
        "status": "passed",
    }
    report_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="E 盘 1.6.6 隔离快照，不得指向生产库")
    parser.add_argument("--target", required=True, help="E 盘清洗副本")
    parser.add_argument("--report", required=True, help="JSON 清洗报告")
    args = parser.parse_args()
    print(json.dumps(clean_snapshot(args.source, args.target, args.report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
