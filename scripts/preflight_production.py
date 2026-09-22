"""Run the Banboos 2.0 production configuration preflight."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.application.deployment_preflight import evaluate_preflight


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Banboos 2.0 deployment declarations")
    parser.add_argument("--strict", action="store_true", help="fail on warnings as well as failures")
    args = parser.parse_args()
    report = evaluate_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = report["status"] == "blocked"
    warned = any(item["status"] == "warn" for item in report["checks"])
    if failed or (args.strict and warned):
        raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())
