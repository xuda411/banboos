"""Run the reproducible financial XLSM release gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.application.financial_release_gate import run_release_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 1.6.6 原版 XLSM 导出是否可发布")
    parser.add_argument("source_template", type=Path)
    parser.add_argument("exported_workbook", type=Path)
    parser.add_argument("--result-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-recalculate", action="store_true",
                        help="只做静态结构检查，不调用 Excel 原生重算")
    parser.add_argument("--recalc-output", type=Path)
    args = parser.parse_args()
    result = json.loads(args.result_json.read_text(encoding="utf-8"))
    report = run_release_gate(
        args.source_template,
        args.exported_workbook,
        result,
        recalculate=not args.no_recalculate,
        recalc_output=args.recalc_output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    checks = {name: value["status"] for name, value in report["checks"].items()}
    print(json.dumps({"status": report["status"], "checks": checks}, ensure_ascii=False))
    return 0 if report["status"] == "RELEASE_READY" else 2 if report["status"] == "PENDING_CROSS_ENGINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

