"""Verify offline PostgreSQL migration SQL and local task recovery semantics."""
from __future__ import annotations

import argparse
import gc
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from apps.worker.main import run_once
from packages.application.run_registry import RunRegistry
from packages.application.sqlite_runtime import SQLiteRuntime


def verify() -> dict:
    migration = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
                               capture_output=True, text=True, check=False)
    with tempfile.TemporaryDirectory(prefix="banboos2-recovery-", ignore_cleanup_errors=True) as directory:
        runtime = SQLiteRuntime(Path(directory) / "runtime.sqlite")
        registry = RunRegistry(runtime, runtime)
        item = registry.submit("noop")
        registry.claim_next(timeout=0)
        recovered = registry.recover_running()
        run_once(registry)
        after_restart = SQLiteRuntime(runtime.path).get(item.run_id)
        del after_restart, registry, runtime
        gc.collect()
        after_restart = SQLiteRuntime(Path(directory) / "runtime.sqlite").get(item.run_id)
    return {"migration_sql": migration.returncode == 0,
            "migration_sql_length": len(migration.stdout),
            "recovered_tasks": recovered,
            "task_status_after_restart": after_restart.status if after_restart else None,
            "status": "passed" if migration.returncode == 0 and recovered == 1
            and after_restart and after_restart.status == "succeeded" else "failed"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="var/migrations/persistence-recovery-report.json")
    args = parser.parse_args()
    report = verify()
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
