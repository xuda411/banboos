"""Structured XLSX export for completed financial tasks."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from packages.application.financial_formula_audit import write_formula_audit

GREEN = "0B6B53"
LIGHT_GREEN = "E8F2EE"
TEXT = "173B35"
THIN = Side(style="thin", color="C9D8D2")


def export_financial_xlsx(result: dict, destination: str | Path) -> Path:
    """Write a typed, reviewable workbook atomically and return its path."""
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True,
                                           forceFullCalc=True)
    overview = workbook.active
    overview.title = "项目概览"
    _write_overview(overview, result)
    _write_parameters(workbook.create_sheet("测算参数"), result)
    _write_cashflow(workbook.create_sheet("年度现金流"), result)
    _write_debt(workbook.create_sheet("融资明细"), result)
    _write_timeline(workbook.create_sheet("全周期现金流"), result)
    _write_template_mapping(workbook.create_sheet("模板映射"))
    write_formula_audit(workbook, result, _title, _header)
    for sheet in workbook.worksheets:
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "B5"
        _fit_columns(sheet)
        sheet.print_title_rows = "1:4"
        sheet.print_options.horizontalCentered = True
        sheet.page_setup.orientation = "landscape" if sheet.max_column > 6 else "portrait"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3 if sheet.max_column > 6 else sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_area = f"A1:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        sheet.row_dimensions[1].height = 32
        sheet.row_dimensions[2].height = 30
        if sheet.title == "公式复核":
            sheet.row_dimensions[2].height = 45
            sheet.column_dimensions["A"].width = 10
            sheet.column_dimensions["B"].width = 12
            for column in range(3, 16):
                sheet.column_dimensions[get_column_letter(column)].width = 23
        sheet.row_dimensions[4].height = 38
        for cells in sheet.iter_rows(min_row=4):
            sheet.row_dimensions[cells[0].row].height = 30
            for cell in cells:
                cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.oddFooter.center.text = "Banboos 2.0 · 第 &P 页 / 共 &N 页"
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
    sheet.cell(2, 1, "Banboos 2.0 · 已完成任务结果快照；修改参数请在软件重新测算后导出")
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
        ("全投资税前 IRR", result.get("full_pre_tax_irr"), "%", "未扣所得税"),
        ("全投资税前 NPV", result.get("full_pre_tax_npv_yuan"), "元", "未扣所得税"),
        ("资本金税前 IRR", result.get("equity_pre_tax_irr"), "%", "未扣所得税"),
        ("资本金税前 NPV", result.get("equity_pre_tax_npv_yuan"), "元", "未扣所得税"),
        ("本次任务 ID", result.get("run_id"), "", "对应导出任务，区别于上游任务"),
        ("计算完成时间", result.get("completed_at"), "UTC", "任务快照时间"),
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
               "项目现金流（元）", "资本金现金流（元）", "应纳税利润（元）", "净利润（元）", "资本金所得税（元）",
               "不含税收入（元）", "销项增值税（元）", "实际应缴增值税（元）", "进项税抵扣使用（元）",
               "进项税抵扣余额（元）", "增值税附加（元）", "印花税（元）", "收益分成（元）", "保险费（元）",
               "项目税前现金流（元）", "资本金税前现金流（元）"]
    _title(sheet, "年度现金流", len(headers))
    _header(sheet, 4, headers)
    keys = ["year", "eol", "energy_revenue_yuan", "capacity_fee_yuan", "subsidy_yuan",
            "capacity_lease_yuan", "primary_frequency_yuan", "secondary_frequency_yuan",
            "revenue_yuan", "operating_cost_yuan", "depreciation_yuan", "income_tax_yuan",
            "replacement_capex_yuan", "project_cashflow_yuan", "equity_cashflow_yuan",
            "taxable_profit_yuan", "net_profit_yuan", "equity_tax_yuan", "net_revenue_yuan",
            "output_vat_yuan", "actual_vat_yuan", "input_vat_credit_used_yuan",
            "input_vat_credit_closing_yuan", "vat_surcharge_yuan", "stamp_tax_yuan",
            "revenue_share_yuan", "insurance_yuan", "project_pre_tax_cashflow_yuan",
            "equity_pre_tax_cashflow_yuan"]
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
        "single_side_efficiency": ("单边系统效率", "%"),
        "dod": ("放电深度 DOD", "%"),
        "annual_cycles": ("年循环次数", "次/年"),
        "eol_method": ("EOL 计算方式", ""),
        "calendar_eol_decline": ("日历衰减率", "%"),
        "cycle_life_cycles": ("循环寿命", "次"),
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
        "land_rent_yuan": ("土地租金", "元/年"),
        "insurance_rate": ("保险费率", "%"),
        "fixed_operation_cost_yuan": ("固定运营费", "元/年"),
        "revenue_share_threshold_yuan": ("收益分成门槛", "元/年"),
        "revenue_share_rate": ("收益分成比例", "%"),
        "other_operating_cost_yuan": ("其他运营费", "元/年"),
        "first_year_eol": ("首年 EOL", "%"),
        "final_eol": ("末年 EOL", "%"),
        "residual_rate": ("残值率", "%"),
        "income_tax_rate": ("所得税率", "%"),
        "vat_rate": ("增值税率", "%"),
        "vat_surcharge_rate": ("增值税附加率", "%"),
        "stamp_tax_rate": ("印花税率", "%"),
        "input_vat_rate_equipment": ("设备进项税率", "%"),
        "input_vat_rate_other": ("其他投资进项税率", "%"),
        "equipment_investment_share": ("设备投资占比", "%"),
        "input_vat_credit_ratio": ("进项税抵扣比例", "%"),
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
                "income_tax_rate", "discount_rate", "loan_ratio", "single_side_efficiency", "dod",
                "calendar_eol_decline", "insurance_rate", "revenue_share_rate", "vat_rate",
                "vat_surcharge_rate", "stamp_tax_rate", "input_vat_rate_equipment",
                "input_vat_rate_other", "equipment_investment_share", "input_vat_credit_ratio",
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
        longest = max((sum(2 if ord(char) > 127 else 1 for char in str(cell.value or ""))
                       for cell in column_cells if cell.row >= 4), default=12)
        sheet.column_dimensions[letter].width = min(max(longest + 2, 16), 48)


def _write_timeline(sheet, result: dict) -> None:
    _title(sheet, "建设期与全周期现金流", 5)
    _header(sheet, 4, ["年度", "项目现金流（元）", "资本金现金流（元）", "累计项目现金流（元）", "累计资本金现金流（元）"])
    cumulative_project = cumulative_equity = 0.0
    for year, (project, equity) in enumerate(zip(result.get("cashflows_yuan", []),
                                               result.get("equity_cashflows_yuan", []), strict=True)):
        cumulative_project += project
        cumulative_equity += equity
        sheet.append([year, project, equity, cumulative_project, cumulative_equity])
        for cell in sheet[sheet.max_row]:
            cell.number_format = "#,##0.00;[Red](#,##0.00);0.00"
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
        sheet.cell(sheet.max_row, 1).number_format = '0" 年"'
    if sheet.max_row > 4:
        chart = LineChart()
        chart.title = "累计现金流（含建设期）"
        chart.y_axis.title = "元"
        chart.x_axis.title = "年度（0 为建设期）"
        chart.add_data(Reference(sheet, min_col=4, max_col=5, min_row=4, max_row=sheet.max_row), titles_from_data=True)
        chart.set_categories(Reference(sheet, min_col=1, min_row=5, max_row=sheet.max_row))
        chart.width, chart.height = 26, 12
        sheet.add_chart(chart, f"A{sheet.max_row + 3}")
        # Include the embedded chart in the print area.
        sheet.cell(sheet.max_row + 27, 5, "期初投资计入第 0 年；金额为任务快照值。")


def _write_template_mapping(sheet) -> None:
    """Document the explicit server-to-xlsm semantic mapping without editing the source template."""
    _title(sheet, "服务器版与 xlsm 模板映射", 5)
    _header(sheet, 4, ["服务器版字段", "单位", "模板工作表", "模板语义", "映射状态"])
    rows = [
        ("power_mw", "MW", "参数设定", "系统功率（MW）", "已映射"),
        ("capacity_mwh", "MWh", "参数设定", "电池容量（MWh）", "已映射"),
        ("annual_revenue_yuan", "元/年", "电量类", "电能量收入", "已映射"),
        ("capex_yuan_per_wh", "元/Wh", "参数设定", "单位投资", "已映射"),
        ("om_rate", "%", "财务指标", "运营成本/运维费率", "已映射"),
        ("first_year_eol / final_eol", "%", "EOL", "生命周期衰减", "规则不同：服务器线性衰减，模板取日历/循环衰减最小值"),
        ("single_side_efficiency / round_trip_efficiency", "%", "参数设定 D5", "效率", "服务器保留单边效率；节点价差任务使用往返效率，禁止直接同值代入"),
        ("dod / annual_cycles / cycle_life_cycles", "%、次", "参数设定 D6/D10", "有效容量与循环衰减", "已接入参数，默认不改变既有年收入口径"),
        ("insurance_rate / fixed_operation_cost_yuan / revenue_share_*", "%、元", "参数设定 D32:D36", "保险、固定运营费、收益分成", "已接入年度运营成本"),
        ("vat_rate / vat_surcharge_rate / stamp_tax_rate", "%", "参数设定 D55:D58", "增值税及附加、印花税", "已接入现金流"),
        ("input_vat_rate_equipment / input_vat_rate_other", "%", "参数设定 D57:D58", "设备及其他投资进项税率", "已接入进项税抵扣余额"),
        ("equipment_investment_share / input_vat_credit_ratio", "%", "参数设定 D57:D58", "进项税抵扣范围", "服务器版显式配置"),
        ("yearly[*]", "元/年", "财务指标", "年度收入、成本、税费和现金流", "服务器明细"),
        ("full_irr / equity_irr", "%", "财务指标", "全投资/资本金 IRR", "服务器结果"),
        ("cashflows_yuan", "元", "财务指标", "项目现金流（含建设期）", "服务器结果"),
    ]
    for row, values in enumerate(rows, 5):
        for col, value in enumerate(values, 1):
            cell = sheet.cell(row, col, value)
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
            cell.fill = PatternFill("solid", fgColor=LIGHT_GREEN if row % 2 else "FFFFFF")
            cell.border = Border(bottom=THIN)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.row_dimensions[row].height = 30
