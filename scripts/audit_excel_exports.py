"""Audit Banboos Excel exports for common layout and template-parity rules.

This is intentionally read-only: it opens generated workbooks and the preserved
1.6.6 template, then writes a compact JSON/Markdown review for release checks.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import load_workbook

from packages.application.financial_release_gate import inspect_workbook_features
from packages.application.spreadsheet_engine import detect_spreadsheet_engines

REQUIRED_FINANCIAL_XLSX = [
    "项目概览", "测算参数", "年度现金流", "融资明细", "全周期现金流",
    "财务指标", "财务模板", "模板复核", "重算复核", "模板映射", "公式复核",
]
REQUIRED_TEMPLATE_SHEETS = ["参数设定 ", "容量类", "电量类 ", "辅助服务类", "EOL", "财务指标"]


def _check_common(path: Path, workbook) -> list[dict]:
    checks = []
    has_source = "导出说明" in workbook.sheetnames
    version = next((row[1].value for row in workbook["导出说明"].iter_rows(min_row=5)
                    if row[0].value == "导出格式版本"), None) if has_source else None
    checks.append({"name": "export_schema_version", "status": "PASS" if version else "WARN", "value": version})
    for sheet in workbook.worksheets:
        checks.append({
            "name": f"sheet:{sheet.title}:content", "status": "PASS" if sheet.max_row >= 4 else "WARN",
            "value": {"rows": sheet.max_row, "columns": sheet.max_column},
        })
        checks.append({
            "name": f"sheet:{sheet.title}:print_and_freeze",
            "status": "PASS" if sheet.print_area and sheet.freeze_panes else "WARN",
            "value": {"print_area": str(sheet.print_area), "freeze_panes": str(sheet.freeze_panes)},
        })
    return checks


def audit(financial_xlsx: Path | None, financial_xlsm: Path | None, export_dir: Path | None,
          input_files: list[Path] | None = None) -> dict:
    files = []
    files.extend(input_files or [])
    if export_dir and export_dir.exists():
        files.extend(sorted(export_dir.glob("*.xlsx")))
    if financial_xlsx:
        files.append(financial_xlsx)
    checks = []
    workbooks = []
    for path in dict.fromkeys(files):
        workbook = load_workbook(path, data_only=False, keep_vba=path.suffix.lower() == ".xlsm")
        workbooks.append(path.name)
        checks.extend({"file": path.name, **item} for item in _check_common(path, workbook))
    if financial_xlsx and financial_xlsx.exists():
        workbook = load_workbook(financial_xlsx, data_only=False)
        actual = workbook.sheetnames
        checks.append({"file": financial_xlsx.name, "name": "financial_xlsx_sheet_set",
                       "status": "PASS" if all(item in actual for item in REQUIRED_FINANCIAL_XLSX) else "FAIL",
                       "value": actual})
        checks.append({"file": financial_xlsx.name, "name": "financial_template_formulas",
                       "status": "PASS" if str(workbook["财务模板"]["D78"].value).startswith("=IRR(") else "FAIL",
                       "value": workbook["财务模板"]["D78"].value})
    if financial_xlsm and financial_xlsm.exists():
        workbook = load_workbook(financial_xlsm, data_only=False, keep_vba=True)
        actual = workbook.sheetnames
        checks.append({"file": financial_xlsm.name, "name": "native_template_sheet_set",
                       "status": "PASS" if all(item in actual for item in REQUIRED_TEMPLATE_SHEETS) else "FAIL",
                       "value": actual})
        checks.append({"file": financial_xlsm.name, "name": "native_input_mapping",
                       "status": "PASS" if workbook["参数设定 "]["D3"].value is not None
                       and workbook["参数设定 "]["D4"].value is not None else "WARN",
                       "value": {"D3": workbook["参数设定 "]["D3"].value,
                                 "D4": workbook["参数设定 "]["D4"].value}})
        checks.append({"file": financial_xlsm.name, "name": "native_feature_inventory",
                       "status": "PASS", "value": inspect_workbook_features(financial_xlsm)})
    failures = [item for item in checks if item["status"] == "FAIL"]
    warnings = [item for item in checks if item["status"] == "WARN"]
    engine = detect_spreadsheet_engines()
    checks.append({"file": "host", "name": "native_recalculation_engine",
                   "status": "PASS" if engine["status"] == "available" else "WARN",
                   "value": engine})
    if engine["status"] != "available":
        warnings.append(checks[-1])
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(), "files": workbooks,
        "checks": checks, "pass": not failures, "failures": len(failures), "warnings": len(warnings),
        "native_recalculation_engine": engine,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--financial-xlsx", type=Path)
    parser.add_argument("--financial-xlsm", type=Path)
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--input", type=Path, action="append", default=[],
                        help="Additional xlsx files to audit; may be repeated")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.financial_xlsx, args.financial_xlsm, args.export_dir, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("pass", "failures", "warnings", "files")}, ensure_ascii=False))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
