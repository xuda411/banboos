"""Structured XLSX export for completed financial tasks."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

GREEN = "0B6B53"
LIGHT_GREEN = "E8F2EE"
TEXT = "173B35"
THIN = Side(style="thin", color="C9D8D2")


def export_financial_xlsx(result: dict, destination: str | Path) -> Path:
    """Write a typed, reviewable workbook atomically and return its path."""
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    overview = workbook.active
    overview.title = "项目概览"
    _write_overview(overview, result)
    _write_parameters(workbook.create_sheet("测算参数"), result)
    _write_cashflow(workbook.create_sheet("年度现金流"), result)
    _write_debt(workbook.create_sheet("融资明细"), result)
    for sheet in workbook.worksheets:
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "A4"
        _fit_columns(sheet)
    with tempfile.NamedTemporaryFile(prefix=f".{target.stem}-", suffix=".xlsx",
                                     dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        workbook.save(temporary)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _title(sheet, title: str, columns: int) -> None:
    sheet.cell(1, 1, title)
    sheet.cell(1, 1).font = Font(name="Microsoft YaHei", size=16, bold=True, color=TEXT)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    sheet.cell(2, 1, "Banboos 2.0 · 结果来自已完成任务，可通过 run_id 回放")
    sheet.cell(2, 1).font = Font(name="Microsoft YaHei", italic=True, color="5B756E")
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)


def _header(sheet, row: int, headers: list[str]) -> None:
    for column, value in enumerate(headers, start=1):
        cell = sheet.cell(row, column, value)
        cell.fill = PatternFill("solid", fgColor=GREEN)
        cell.font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(bottom=THIN)


def _write_overview(sheet, result: dict) -> None:
    _title(sheet, "独立储能项目财务测算", 4)
    _header(sheet, 4, ["指标", "数值", "单位", "说明"])
    rows = [
        ("任务来源", result.get("source_run_id") or "直接输入", "", "可通过 run_id 追溯上游调度"),
        ("模型版本", result.get("model_version", ""), "", "领域模型版本"),
        ("额定功率", result.get("power_mw"), "MW", ""),
        ("额定容量", result.get("capacity_mwh"), "MWh", ""),
        ("系统时长", result.get("duration_hours"), "h", "容量 ÷ 功率"),
        ("初始投资", result.get("initial_investment_yuan"), "元", ""),
        ("建设期利息", result.get("construction_interest_yuan"), "元", ""),
        ("总投资", result.get("total_investment_yuan"), "元", ""),
        ("全投资 IRR", result.get("full_irr"), "%", "现金流结果"),
        ("全投资 NPV", result.get("full_npv_yuan"), "元", "按折现率计算"),
        ("全投资回收期", result.get("payback_year"), "年", "静态回收期"),
        ("资本金 IRR", result.get("equity_irr"), "%", "含贷款还本付息"),
        ("资本金 NPV", result.get("equity_npv_yuan"), "元", "含贷款还本付息"),
    ]
    for row, values in enumerate(rows, start=5):
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row, column, value)
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
            cell.fill = PatternFill("solid", fgColor=LIGHT_GREEN if row % 2 else "FFFFFF")
            cell.border = Border(bottom=THIN)
            if column == 2 and isinstance(value, (int, float)):
                cell.number_format = "0.00%" if "IRR" in str(values[0]) else "#,##0.00"


def _write_cashflow(sheet, result: dict) -> None:
    headers = ["年度", "EOL", "电能量收入（元）", "容量电费（元）", "补贴（元）",
               "容量租赁（元）", "一次调频（元）", "二次调频（元）", "总收入（元）",
               "运营成本（元）", "折旧（元）", "所得税（元）", "换电池投资（元）",
               "项目现金流（元）", "资本金现金流（元）"]
    _title(sheet, "年度现金流", len(headers))
    _header(sheet, 4, headers)
    keys = ["year", "eol", "energy_revenue_yuan", "capacity_fee_yuan", "subsidy_yuan",
            "capacity_lease_yuan", "primary_frequency_yuan", "secondary_frequency_yuan",
            "revenue_yuan", "operating_cost_yuan", "depreciation_yuan", "income_tax_yuan",
            "replacement_capex_yuan", "project_cashflow_yuan", "equity_cashflow_yuan"]
    for row, item in enumerate(result.get("yearly", []), start=5):
        for column, key in enumerate(keys, start=1):
            cell = sheet.cell(row, column, item.get(key))
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
            cell.border = Border(bottom=THIN)
            if key == "eol":
                cell.number_format = "0.0%"
            elif key != "year":
                cell.number_format = "#,##0.00"
    if result.get("yearly"):
        sheet.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{4 + len(result['yearly'])}"


def _write_parameters(sheet, result: dict) -> None:
    labels = {
        "power_mw": ("额定功率", "MW"),
        "capacity_mwh": ("额定容量", "MWh"),
        "annual_revenue_yuan": ("首年电能量收入", "元"),
        "capacity_lease_yuan": ("容量租赁收入", "元/年"),
        "capacity_fee_yuan": ("容量电费收入", "元/年"),
        "subsidy_yuan": ("补贴收入", "元/年"),
        "primary_frequency_yuan": ("一次调频收入", "元/年"),
        "secondary_frequency_yuan": ("二次调频收入", "元/年"),
        "capex_yuan_per_wh": ("单位投资", "元/Wh"),
        "operation_years": ("运营年限", "年"),
        "om_rate": ("运维费率", "%"),
        "om_growth": ("运维费增长率", "%"),
        "first_year_eol": ("首年 EOL", "%"),
        "final_eol": ("末年 EOL", "%"),
        "residual_rate": ("残值率", "%"),
        "income_tax_rate": ("所得税率", "%"),
        "discount_rate": ("折现率", "%"),
        "loan_ratio": ("贷款比例", "%"),
        "loan_years": ("贷款期限", "年"),
        "loan_rate": ("贷款利率", "%"),
        "construction_years": ("建设期", "年"),
        "construction_loan_rate": ("建设期贷款利率", "%"),
        "replace_year": ("换电池年份", "年"),
        "replace_capex_yuan": ("换电池投资", "元"),
        "source_run_id": ("上游任务", "run_id"),
    }
    _title(sheet, "测算参数与口径", 4)
    _header(sheet, 4, ["参数", "数值", "单位", "说明"])
    parameters = result.get("input_parameters", {})
    for row, (key, (label, unit)) in enumerate(labels.items(), start=5):
        value = parameters.get(key)
        cell_values = [label, value, unit, key]
        for column, value in enumerate(cell_values, start=1):
            cell = sheet.cell(row, column, value)
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
            cell.fill = PatternFill("solid", fgColor=LIGHT_GREEN if row % 2 else "FFFFFF")
            cell.border = Border(bottom=THIN)
            if column == 2 and key.endswith("rate") or column == 2 and key in {
                "om_rate", "om_growth", "first_year_eol", "final_eol", "residual_rate",
                "income_tax_rate", "discount_rate", "loan_ratio",
            }:
                cell.number_format = "0.00%"
            elif column == 2 and isinstance(value, (int, float)):
                cell.number_format = "#,##0.00"


def _write_debt(sheet, result: dict) -> None:
    headers = ["年度", "贷款利息（元）", "偿还本金（元）", "剩余贷款（元）", "资本金现金流（元）"]
    _title(sheet, "融资明细", len(headers))
    _header(sheet, 4, headers)
    keys = ["year", "loan_interest_yuan", "loan_principal_yuan", "remaining_loan_yuan", "equity_cashflow_yuan"]
    for row, item in enumerate(result.get("yearly", []), start=5):
        for column, key in enumerate(keys, start=1):
            cell = sheet.cell(row, column, item.get(key))
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
            cell.border = Border(bottom=THIN)
            if key != "year":
                cell.number_format = "#,##0.00"


def _fit_columns(sheet) -> None:
    for column_cells in sheet.columns:
        letter = get_column_letter(column_cells[0].column)
        longest = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[letter].width = min(max(longest + 2, 12), 26)
