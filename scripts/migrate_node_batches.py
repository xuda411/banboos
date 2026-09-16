"""Migrate and reconcile a bounded set of high-coverage legacy nodes."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from packages.application.financial_replay import replay_financial_baselines
from packages.application.legacy_migration import migrate_legacy_snapshot, verified_snapshot
from packages.application.legacy_reconciliation import reconcile_legacy_migration


def choose_scopes(snapshot: Path, limit: int, market: str | None) -> list[tuple[int, str]]:
    if not 1 <= limit <= 100:
        raise ValueError("limit-nodes 必须为 1–100")
    if market is not None and market not in {"日前", "实时"}:
        raise ValueError("market 必须是 日前 或 实时")
    markets = [market] if market else ["日前", "实时"]
    with closing(sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        placeholders = ",".join("?" for _ in markets)
        node_ids = [row[0] for row in connection.execute(
            f"SELECT node_id, COUNT(*) AS records FROM price_data "
            f"WHERE case_type IN ({placeholders}) GROUP BY node_id "
            "ORDER BY records DESC, node_id LIMIT ?", [*markets, limit],
        )]
        scopes = []
        for node_id in node_ids:
            available = {row[0] for row in connection.execute(
                "SELECT DISTINCT case_type FROM price_data WHERE node_id=?", (node_id,)
            )}
            scopes.extend((node_id, item_market) for item_market in markets if item_market in available)
    return scopes


def run_batches(manifest_path, target_path, report_path, limit=10, market=None,
                max_records=5000) -> dict:
    manifest, snapshot = verified_snapshot(manifest_path)
    destination = Path(report_path).resolve()
    protected = [snapshot, Path(manifest_path).resolve(), Path(target_path).resolve(),
                 Path(manifest["source_path"]).resolve()]
    if destination in protected or (destination.exists() and any(
            destination.samefile(p) for p in protected if p.exists())):
        raise ValueError("报告不能覆盖数据库、快照或清单")
    scopes = choose_scopes(snapshot, limit, market)
    output = {"status": "running", "snapshot_sha256": manifest["sha256"],
              "planned_scopes": len(scopes), "scopes": []}
    destination.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = destination.with_name(destination.name + "." + uuid4().hex + ".tmp")
        temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False),
                             encoding="utf-8")
        temporary.replace(destination)

    save()
    for node_id, item_market in scopes:
        item = {"node_id": node_id, "market": item_market}
        try:
            item["migration"] = migrate_legacy_snapshot(manifest_path, target_path,
                node_id=node_id, market=item_market, max_records=max_records)
            report = reconcile_legacy_migration(manifest_path, target_path,
                node_id=node_id, market=item_market)
            item["reconciliation"] = report
            item["financial_replay"] = replay_financial_baselines(report["baselines"])
            item["status"] = "matched" if (report["status"] == "matched" and
                item["financial_replay"]["status"] == "matched") else "difference"
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
            # Persist failure evidence and continue independent nodes; reruns reuse successful scopes.
            item.update(status="failed", error=str(error))
        output["scopes"].append(item)
        save()
    output["status"] = "matched" if output["scopes"] and all(
        item["status"] == "matched" for item in output["scopes"]) else "difference"
    save()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--target", required=True)
    parser.add_argument("--limit-nodes", type=int, default=10)
    parser.add_argument("--market", choices=["日前", "实时"])
    parser.add_argument("--max-records", type=int, default=5000)
    parser.add_argument("--report", default="var/migrations/node-batch-report.json")
    args = parser.parse_args()
    output = run_batches(args.manifest, args.target, args.report, args.limit_nodes,
                         args.market, args.max_records)
    print(json.dumps({"status": output["status"], "scopes": len(output["scopes"]),
                      "report": str(Path(args.report).resolve())}, ensure_ascii=False))
    if output["status"] != "matched":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
