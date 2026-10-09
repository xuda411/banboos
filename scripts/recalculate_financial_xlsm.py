"""Recalculate an XLSM copy with the installed native spreadsheet engine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.application.spreadsheet_engine import recalculate_xlsm

# Keep the historical script API stable for tests and callers.
recalculate = recalculate_xlsm


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    destination = args.output or args.source.with_name(args.source.stem + ".recalculated.xlsm")
    result = recalculate(args.source, destination, args.timeout)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")
    return 0 if result["status"] == "recalculated" else 2 if result["status"] == "unavailable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
