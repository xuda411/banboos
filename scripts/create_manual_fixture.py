"""Create a deterministic, read-only staging fixture for positive manual checks.

The fixture is deliberately separate from production data. It contains two
nodes, both market types, and a complete 2026 history of 96-point curves so
the curve, annual spread, dispatch and portfolio screens can be verified with
real rows instead of fabricated API responses.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, timedelta
from math import cos, pi, sin
from pathlib import Path
from uuid import uuid4

from packages.application.legacy_migration import migrate_legacy_snapshot
from packages.application.legacy_snapshot import snapshot_legacy_database
from packages.infrastructure.database_fields import PRICE_FIELDS


def create_fixture(target: Path) -> dict:
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_name(f".{target.stem}.legacy-{uuid4().hex[:8]}.sqlite3")
    snapshots = target.parent / "fixture-snapshots"
    target.unlink(missing_ok=True)
    fields = ",".join(f"{name} REAL" for name in PRICE_FIELDS)
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY, node_name TEXT NOT NULL, province TEXT)")
        connection.execute("CREATE TABLE price_data (id INTEGER PRIMARY KEY, node_id INTEGER, run_date TEXT, publish_type TEXT, case_type TEXT, " + fields + ", source_file TEXT)")
        connection.executemany("INSERT INTO nodes VALUES (?,?,?)", [(1, "人工测试节点·湖北", "湖北"), (2, "人工测试节点·广东", "广东")])
        columns = ["id", "node_id", "run_date", "publish_type", "case_type", *PRICE_FIELDS, "source_file"]
        statement = f"INSERT INTO price_data ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
        row_id = 1
        current = date(2026, 1, 1)
        while current <= date(2026, 12, 31):
            day_index = (current - date(2026, 1, 1)).days
            for node_id in (1, 2):
                for market_index, market in enumerate(("日前", "实时")):
                    prices = []
                    for slot in range(96):
                        hour = slot / 4
                        morning = max(0.0, sin((hour - 6.0) / 12.0 * pi))
                        evening = max(0.0, sin((hour - 15.0) / 9.0 * pi))
                        seasonal = 14.0 * cos(day_index / 365.0 * 2.0 * pi)
                        node_bias = 18.0 if node_id == 2 else 0.0
                        market_bias = 9.0 if market_index else 0.0
                        value = 235.0 + node_bias + market_bias + seasonal + 125.0 * evening - 80.0 * morning
                        prices.append(round(value, 3))
                    connection.execute(statement, [row_id, node_id, current.isoformat(), "历史导入", market, *prices, f"manual-fixture-{node_id}.csv"])
                    row_id += 1
            current += timedelta(days=1)
    manifest = snapshot_legacy_database(source, snapshots)
    result = migrate_legacy_snapshot(manifest, target)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("var/manual-check/positive-staging.sqlite3"))
    args = parser.parse_args()
    print(create_fixture(args.target))


if __name__ == "__main__":
    main()
