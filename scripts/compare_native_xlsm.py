"""Compare an exported 1.6.6 XLSM cache with a server financial snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.application.financial_xlsm_review import review_native_cached_values
from packages.application.spreadsheet_engine import detect_spreadsheet_engines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--result-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--native", action="store_true",
                        help="标记工作簿已由 Excel/WPS 原生重算")
    args = parser.parse_args()
    result = json.loads(args.result_json.read_text(encoding="utf-8"))
    report = review_native_cached_values(
        args.workbook,
        result,
        engine_executed=args.native,
        native_engine=detect_spreadsheet_engines() if args.native else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"]}, ensure_ascii=False))
    return 0 if report["status"] == "CACHED_VALUES_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
