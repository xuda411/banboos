"""Structured XLSX export for completed financial tasks."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from packages.application.financial_formula_audit import write_formula_audit
from packages.application.financial_template_audit import write_template_audit

GREEN = "0B6B53"
LIGHT_GREEN = "E8F2EE"
TEXT = "173B35"
TEMPLATE_HEADER = "B4C6E7"
TEMPLATE_SECTION = "FFF2CC"
TEMPLATE_TEXT = "404040"
TEMPLATE_ALERT = "C00000"
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
    _write_template_financial_sheet(workbook.create_sheet("财务指标"), result)
    _write_template_parity_sheet(workbook.create_sheet("财务模板"), result)
    if result.get("input_parameters", {}).get("revenue_phases"):
        _write_revenue_phase_sheet(workbook.create_sheet("阶段收益"), result)
    write_template_audit(workbook)
    _write_template_mapping(workbook.create_sheet("模板映射"))
    write_formula_audit(workbook, result, _title, _header)
    for sheet in workbook.worksheets:
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "D5" if sheet.title == "财务指标" else ("D3" if sheet.title == "财务模板" else "B5")
        _fit_columns(sheet)
        sheet.print_title_rows = "1:2" if sheet.title == "财务模板" else "1:4"
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
        "revenue_phases": ("分阶段收益规则", "JSON"),
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
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
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


def _write_revenue_phase_sheet(sheet, result: dict) -> None:
    """Expand phase rules into annual formulas that the audit sheet can reuse."""
    parameters = result.get("input_parameters", {})
    phases = parameters.get("revenue_phases", {})
    years = int(parameters.get("operation_years", 0))
    components = [
        ("annual_revenue_yuan", True), ("capacity_lease_yuan", False),
        ("capacity_fee_yuan", True), ("subsidy_yuan", True),
        ("primary_frequency_yuan", False), ("secondary_frequency_yuan", False),
    ]
    _title(sheet, "分阶段收益年度展开", 8)
    _header(sheet, 4, ["收入项目", "年份", "开始年份", "结束年份", "按 EOL", "年度增长", "基准收入（元）", "阶段收入（元）"])
    # The parameter sheet is stable and keyed by column D; locate it without
    # relying on row numbers so added fields do not break the formulas.
    source = sheet.parent["测算参数"]
    parameter_rows = {source.cell(row, 4).value: row
                      for row in range(5, source.max_row + 1)}
    row = 5
    for component, default_eol in components:
        rule = phases.get(component) or {
            "start_year": 1, "end_year": None,
            "eol_applies": default_eol, "annual_growth": 0,
        }
        base_ref = f"'测算参数'!$B${parameter_rows[component]}"
        for year in range(1, years + 1):
            values = [component, year, rule["start_year"], rule.get("end_year"),
                      1 if rule.get("eol_applies", default_eol) else 0,
                      rule.get("annual_growth", 0), f"={base_ref}"]
            for column, value in enumerate(values, start=1):
                cell = sheet.cell(row, column, value)
                cell.font = Font(name="Microsoft YaHei", color=TEXT)
                cell.border = Border(bottom=THIN)
                if column == 6:
                    cell.number_format = "0.00%"
                elif column == 7:
                    cell.number_format = "#,##0.00"
            audit_row = year + 4
            sheet.cell(row, 8,
                       f'=IF(AND(B{row}>=C{row},OR(D{row}="",B{row}<=D{row})),G{row}*(1+F{row})^(B{row}-C{row})*IF(E{row}=1,\'公式复核\'!B{audit_row},1),0)')
            sheet.cell(row, 8).number_format = "#,##0.00"
            sheet.cell(row, 8).font = Font(name="Microsoft YaHei", color=TEXT)
            sheet.cell(row, 8).border = Border(bottom=THIN)
            row += 1
    sheet.auto_filter.ref = f"A4:H{row - 1}"


def _write_template_financial_sheet(sheet, result: dict) -> None:
    """Render a horizontal, template-like financial indicator statement."""
    yearly = result.get("yearly", [])
    years = len(yearly)
    last_column = 4 + years
    _title(sheet, "财务指标（模板排版）", last_column)
    sheet.cell(2, 1, "年度横向展示；明细和税务口径均链接到任务快照与公式复核页")
    _header(sheet, 4, ["序号", "指标", "单位"] + [0] + list(range(1, years + 1)))
    for column in range(4, last_column + 1):
        sheet.cell(4, column).number_format = '0" 年"'
    rows = [
        (5, "收益", "", None), (6, "EOL", "%", "eol"),
        (7, "电能量收入", "元", "energy_revenue_yuan"),
        (8, "容量租赁收入", "元", "capacity_lease_yuan"),
        (9, "容量电费收入", "元", "capacity_fee_yuan"),
        (10, "补贴收入", "元", "subsidy_yuan"),
        (11, "一次调频收入", "元", "primary_frequency_yuan"),
        (12, "二次调频收入", "元", "secondary_frequency_yuan"),
        (13, "总收入", "元", "revenue_yuan"),
        (14, "不含税收入", "元", "net_revenue_yuan"),
        (15, "销项增值税", "元", "output_vat_yuan"),
        (16, "实际应缴增值税", "元", "actual_vat_yuan"),
        (17, "进项税抵扣使用", "元", "input_vat_credit_used_yuan"),
        (18, "进项税抵扣余额", "元", "input_vat_credit_closing_yuan"),
        (20, "成本与税费", "", None),
        (21, "运营成本", "元", "operating_cost_yuan"),
        (22, "折旧", "元", "depreciation_yuan"),
        (23, "换电池投资", "元", "replacement_capex_yuan"),
        (24, "贷款利息", "元", "loan_interest_yuan"),
        (25, "偿还本金", "元", "loan_principal_yuan"),
        (26, "所得税", "元", "income_tax_yuan"),
        (27, "增值税附加", "元", "vat_surcharge_yuan"),
        (28, "印花税", "元", "stamp_tax_yuan"),
        (30, "现金流", "", None),
        (31, "项目税前现金流", "元", "project_pre_tax_cashflow_yuan"),
        (32, "项目现金流", "元", "project_cashflow_yuan"),
        (33, "资本金税前现金流", "元", "equity_pre_tax_cashflow_yuan"),
        (34, "资本金现金流", "元", "equity_cashflow_yuan"),
        (35, "累计项目现金流", "元", "cumulative_project"),
        (36, "累计资本金现金流", "元", "cumulative_equity"),
        (38, "财务指标", "", None),
        (39, "全投资税前 IRR", "%", "full_pre_tax_irr"),
        (40, "全投资 IRR", "%", "full_irr"),
        (41, "全投资税前 NPV", "元", "full_pre_tax_npv_yuan"),
        (42, "全投资 NPV", "元", "full_npv_yuan"),
        (43, "资本金税前 IRR", "%", "equity_pre_tax_irr"),
        (44, "资本金 IRR", "%", "equity_irr"),
        (45, "资本金税前 NPV", "元", "equity_pre_tax_npv_yuan"),
        (46, "资本金 NPV", "元", "equity_npv_yuan"),
    ]
    annual_columns = {
        "eol": "B", "energy_revenue_yuan": "C", "capacity_lease_yuan": "F",
        "capacity_fee_yuan": "D", "subsidy_yuan": "E", "primary_frequency_yuan": "G",
        "secondary_frequency_yuan": "H", "revenue_yuan": "I", "net_revenue_yuan": "S",
        "output_vat_yuan": "T", "actual_vat_yuan": "U", "input_vat_credit_used_yuan": "V",
        "input_vat_credit_closing_yuan": "W", "operating_cost_yuan": "J", "depreciation_yuan": "K",
        "replacement_capex_yuan": "M", "loan_interest_yuan": "?", "loan_principal_yuan": "?",
        "income_tax_yuan": "L", "vat_surcharge_yuan": "X", "stamp_tax_yuan": "Y",
        "project_pre_tax_cashflow_yuan": "AB", "project_cashflow_yuan": "N",
        "equity_pre_tax_cashflow_yuan": "AC", "equity_cashflow_yuan": "O",
    }
    # Loan details live on a separate sheet; resolve their columns through the
    # same year index when writing the annual rows.
    debt_columns = {"loan_interest_yuan": "B", "loan_principal_yuan": "C"}
    for number, label, unit, key in rows:
        sheet.cell(number, 1, "" if key is None else number - 5)
        sheet.cell(number, 2, label)
        sheet.cell(number, 3, unit)
        for column in range(1, 4):
            cell = sheet.cell(number, column)
            cell.font = Font(name="Microsoft YaHei", color=TEXT, bold=key is None)
            cell.border = Border(bottom=THIN)
            cell.fill = PatternFill("solid", fgColor="DDEBE5" if key is None else (LIGHT_GREEN if number % 2 else "FFFFFF"))
        if key is None:
            sheet.merge_cells(start_row=number, start_column=1, end_row=number, end_column=last_column)
            sheet.cell(number, 1).alignment = Alignment(horizontal="left", vertical="center")
            continue
        for year_index in range(years + 1):
            column = 4 + year_index
            cell = sheet.cell(number, column)
            if key in {"full_pre_tax_irr", "full_irr", "equity_pre_tax_irr", "equity_irr",
                       "full_pre_tax_npv_yuan", "full_npv_yuan", "equity_pre_tax_npv_yuan", "equity_npv_yuan"}:
                if column == 4:
                    source_cell = {"full_pre_tax_irr": "B14", "full_irr": "B12",
                                   "full_pre_tax_npv_yuan": "B15", "full_npv_yuan": "B13",
                                   "equity_pre_tax_irr": "B16", "equity_irr": "B9",
                                   "equity_pre_tax_npv_yuan": "B17", "equity_npv_yuan": "B10"}[key]
                    cell.value = f"='项目概览'!{source_cell}"
                else:
                    cell.value = ""
            elif key == "cumulative_project" or key == "cumulative_equity":
                cash_key = "project_cashflow_yuan" if key == "cumulative_project" else "equity_cashflow_yuan"
                source_col = "B" if key == "cumulative_project" else "C"
                if column == 4:
                    cell.value = f"='全周期现金流'!{source_col}5"
                else:
                    cell.value = f"={sheet.cell(number, column - 1).coordinate}+{sheet.cell(32 if cash_key == 'project_cashflow_yuan' else 34, column).coordinate}"
            elif key in debt_columns:
                if column == 4:
                    cell.value = "=0"
                else:
                    cell.value = f"='融资明细'!{debt_columns[key]}{year_index + 4}"
            elif column == 4:
                if key in {"project_pre_tax_cashflow_yuan", "project_cashflow_yuan"}:
                    cell.value = "='全周期现金流'!B5"
                elif key in {"equity_pre_tax_cashflow_yuan", "equity_cashflow_yuan"}:
                    cell.value = "='全周期现金流'!C5"
                else:
                    cell.value = "=1" if key == "eol" else "=0"
            else:
                cell.value = f"='年度现金流'!{annual_columns[key]}{year_index + 4}"
            cell.font = Font(name="Microsoft YaHei", color=TEXT)
            cell.border = Border(bottom=THIN)
            cell.number_format = "0.00%" if unit == "%" or key == "eol" else "#,##0.00;[Red](#,##0.00);0.00"
    # Replace summary cells with recalculable formulas using the horizontal cashflow rows.
    parameter_rows = {sheet.parent["测算参数"].cell(row, 4).value: row
                      for row in range(5, sheet.parent["测算参数"].max_row + 1)}
    discount_ref = f"'测算参数'!$B${parameter_rows['discount_rate']}"
    final_column = get_column_letter(last_column)
    sheet["D39"] = f"=IRR(D31:{final_column}31)"
    sheet["D40"] = f"=IRR(D32:{final_column}32)"
    sheet["D41"] = f"=NPV({discount_ref},E31:{final_column}31)+D31"
    sheet["D42"] = f"=NPV({discount_ref},E32:{final_column}32)+D32"
    sheet["D43"] = f"=IRR(D33:{final_column}33)"
    sheet["D44"] = f"=IRR(D34:{final_column}34)"
    sheet["D45"] = f"=NPV({discount_ref},E33:{final_column}33)+D33"
    sheet["D46"] = f"=NPV({discount_ref},E34:{final_column}34)+D34"
    for row in range(39, 47):
        sheet.cell(row, 4).number_format = "0.00%" if row in {39, 40, 43, 44} else "#,##0.00;[Red](#,##0.00);0.00"
    sheet.auto_filter.ref = f"A4:{get_column_letter(last_column)}46"


def _write_template_parity_sheet(sheet, result: dict) -> None:
    """Render the server result in the row/column shape of the supplied xlsm template."""
    yearly = result.get("yearly", [])
    years = len(yearly)
    last_year_column = 4 + years
    total_column = last_year_column + 1
    last_year_letter = get_column_letter(last_year_column)
    total_letter = get_column_letter(total_column)
    sheet.cell(1, 1, "独立储能项目收益测算具体明细（服务器模板对照）")
    sheet.cell(1, 1).font = Font(name="Microsoft YaHei", size=16, bold=False, color=TEMPLATE_TEXT)
    sheet.cell(1, 1).fill = PatternFill("solid", fgColor=TEMPLATE_HEADER)
    sheet.cell(1, 1).alignment = Alignment(horizontal="center", vertical="center")
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_column)
    headers = ["类别", "序号", "指标与参数", 0] + list(range(1, years + 1)) + ["合计"]
    _header(sheet, 2, headers)
    for column in range(4, last_year_column + 1):
        sheet.cell(2, column).number_format = '0" 年"'

    parameter_rows = {sheet.parent["测算参数"].cell(row, 4).value: row
                      for row in range(5, sheet.parent["测算参数"].max_row + 1)}

    def parameter_ref(key: str) -> str:
        row = parameter_rows.get(key)
        return f"'测算参数'!$B${row}" if row else "0"

    def source_formula(column: int, source_row: int, *, divisor: int | None = 10000) -> str:
        source = f"'财务指标'!{get_column_letter(column)}{source_row}"
        return f"={source}" if divisor is None else f"={source}/{divisor}"

    def annual_cashflow_formula(column: int, source_column: str) -> str:
        # Output column E corresponds to the first operating-year row 5.
        return f"='年度现金流'!{source_column}{column}/10000"

    def set_year(row: int, column: int, formula: str, *, percent: bool = False) -> None:
        cell = sheet.cell(row, column, formula)
        cell.font = Font(name="Microsoft YaHei", size=9,
                         color=TEMPLATE_ALERT if row in {65, 78} else TEMPLATE_TEXT)
        cell.border = Border(left=THIN, right=THIN, bottom=THIN)
        cell.alignment = Alignment(horizontal="right", vertical="center")
        cell.number_format = "0.00%" if percent else "#,##0.00;[Red](#,##0.00);0.00"

    # The labels and row numbers intentionally follow the original 财务指标 sheet.
    row_labels = {
        3: ("1、项目充放电数据与收支明细", "", ""),
        4: ("1、储能 EOL", 1, "电池容量衰减 EOL"), 5: ("", 2, "年平均 EOL"),
        6: ("2、收益", 1, "容量租赁收益（万元）"), 7: ("", 2, "容量电费收益（万元）"),
        8: ("", 3, "容量电费收益-EOL（万元）"), 9: ("", 4, "容量电费浮动比例"),
        10: ("", 5, "容量电费收益-最终（万元）"), 11: ("", 6, "电能量收益（万元）"),
        12: ("", 7, "电能量收益-EOL（万元）"), 13: ("", 8, "电能量收益浮动比例"),
        14: ("", 9, "电能量收益-最终（万元）"), 15: ("", 10, "政策性补贴收益（万元）"),
        16: ("", 11, "政策性补贴收益-EOL（万元）"), 17: ("", 12, "政策性补贴浮动比例"),
        18: ("", 13, "政策性补贴收益-最终（万元）"), 19: ("", 14, "一次调频收益（万元）"),
        20: ("", 15, "一次调频收益-EOL（万元）"), 21: ("", 16, "一次调频收益浮动比例"),
        22: ("", 17, "一次调频收益-最终（万元）"), 23: ("", 18, "二次调频收益（万元）"),
        24: ("", 19, "二次调频收益-EOL（万元）"), 25: ("", 20, "二次调频收益浮动比例"),
        26: ("", 21, "二次调频收益-最终（万元）"), 27: ("", 22, "收益合计（万元）"),
        28: ("", "", "不含税收益"), 29: ("3、折旧费用", 1, "折旧费用（万元）"),
        30: ("", 2, "累计折旧（万元）"), 31: ("", 3, "固定资产残值（万元）"),
        32: ("", 4, "残值（万元）"), 33: ("4、运营成本", 1, "土地租赁费用（万元）"),
        34: ("", 2, "运维费（万元）"), 35: ("", 3, "保险费（万元）"),
        36: ("", 4, "运营费-固定部分（万元）"), 37: ("", 5, "运营费-比例分成部分（万元）"),
        38: ("", 6, "其他费用（万元）"), 39: ("", 7, "换电池费用（万元）"),
        40: ("", 8, "总运营费用（万元）"), 41: ("5、银行融资", 1, "贷款本金（万元）"),
        42: ("", 2, "本年付息（万元）"), 43: ("", 3, "本年还本（万元）"),
        44: ("", 4, "本息合计（万元）"), 45: ("6、税费及抵扣", 1, "应缴纳增值税（万元）"),
        46: ("", 2, "可抵扣固定资产额（万元）"), 47: ("", 3, "固定资产抵扣（万元）"),
        48: ("", 4, "实缴增值税（万元）"), 49: ("", 5, "增值税附加（万元）"),
        50: ("", 6, "印花税（万元）"), 51: ("", 7, "项目利润（万元）"),
        52: ("", 8, "所得税费用（万元）"), 53: ("", 9, "项目净利润（万元）"),
        54: ("2、融资模式下收益分析", "", ""), 55: ("现金流与投资收益", 1, "现金流入（万元）"),
        56: ("", 2, "现金流出（万元）"), 57: ("", 3, "包括：运营成本"),
        58: ("", 4, "贷款本息"), 59: ("", 5, "增值税费用"), 60: ("", 6, "增值税附加"),
        61: ("", 7, "印花税"), 62: ("", 8, "所得税费用"), 63: ("", 9, "现金净流入（万元）"),
        64: ("", 10, "累计现金净流入（万元）"), 65: ("", 11, "所得税前内部收益率 IRR（%）"),
        66: ("", 12, "净现值 NPV（万元）"), 67: ("", 13, "项目回收周期（年）"),
        68: ("3、全投资模式下收益分析", "", ""), 69: ("现金流与投资收益", 1, "现金流入（万元）"),
        70: ("", 2, "现金流出（万元）"), 71: ("", 3, "包括：运营成本"), 72: ("", 4, "增值税费用"),
        73: ("", 5, "所得税费用"), 74: ("", 6, "增值税附加"), 75: ("", 7, "印花税"),
        76: ("", 8, "现金净流入（万元）"), 77: ("", 9, "累计现金净流入（万元）"),
        78: ("", 10, "所得税前内部收益率 IRR（%）"), 79: ("", 11, "净现值 NPV（万元）"),
        80: ("", 12, "项目回收周期（年）"),
    }
    section_rows = {3, 54, 68}
    for row in range(3, 81):
        category, sequence, label = row_labels.get(row, ("", "", ""))
        sheet.cell(row, 1, category)
        sheet.cell(row, 2, sequence)
        sheet.cell(row, 3, label)
        is_section = row in section_rows
        if is_section:
            sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        for column in range(1, total_column + 1):
            cell = sheet.cell(row, column)
            cell.font = Font(name="Microsoft YaHei", size=9, color=TEMPLATE_TEXT, bold=is_section or column == 3)
            cell.fill = PatternFill("solid", fgColor=TEMPLATE_SECTION if is_section else "FFFFFF")
            cell.border = Border(top=THIN if is_section else Side(style=None), bottom=THIN)
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    # Match the original template's compact category hierarchy instead of
    # repeating the category label on every detail row.
    for start, end in ((4, 5), (6, 27), (29, 32), (33, 40), (41, 44),
                       (45, 53), (55, 67), (69, 80)):
        sheet.merge_cells(start_row=start, start_column=1, end_row=end, end_column=1)
        sheet.cell(start, 1).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    for row in section_rows:
        sheet.cell(row, 1).alignment = Alignment(horizontal="left", vertical="center")
    for column in range(1, total_column + 1):
        header = sheet.cell(2, column)
        header.fill = PatternFill("solid", fgColor=TEMPLATE_HEADER)
        header.font = Font(name="Microsoft YaHei", size=9, bold=True, color=TEMPLATE_TEXT)
        header.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        header.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    # The existing server sheet is the calculation owner. This sheet only adapts
    # the unit, row order and labels to the xlsm layout so the two can be audited.
    source_rows = {
        "eol": (6, None), "capacity_lease": (8, 10000), "capacity_fee": (9, 10000),
        "energy": (7, 10000), "subsidy": (10, 10000), "primary": (11, 10000),
        "secondary": (12, 10000), "revenue": (13, 10000), "net_revenue": (14, 10000),
        "output_vat": (15, 10000), "actual_vat": (16, 10000), "credit_used": (17, 10000),
        "credit_closing": (18, 10000), "operating_cost": (21, 10000), "depreciation": (22, 10000),
        "replacement": (23, 10000), "interest": (24, 10000), "principal": (25, 10000),
        "income_tax": (26, 10000), "vat_surcharge": (27, 10000), "stamp_tax": (28, 10000),
        "project_pre_tax": (31, 10000), "project_cashflow": (32, 10000),
        "equity_pre_tax": (33, 10000), "equity_cashflow": (34, 10000),
        "cumulative_project": (35, 10000), "cumulative_equity": (36, 10000),
    }

    def src(name: str, column: int) -> str:
        row, divisor = source_rows[name]
        return source_formula(column, row, divisor=divisor)

    def amount_from_cashflow(column: int, source_column: str) -> str:
        return annual_cashflow_formula(column, source_column)

    def write_row(row: int, formula_builder, *, percent: bool = False, total: bool = False) -> None:
        for year_index, column in enumerate(range(4, last_year_column + 1)):
            set_year(row, column, formula_builder(year_index, column), percent=percent)
        if total:
            set_year(row, total_column, f"=SUM(E{row}:{last_year_letter}{row})", percent=percent)

    write_row(4, lambda _i, column: src("eol", column), percent=True)
    write_row(5, lambda _i, column: src("eol", column), percent=True)
    write_row(6, lambda _i, column: src("capacity_lease", column), total=True)
    write_row(7, lambda _i, column: src("capacity_fee", column), total=True)
    write_row(8, lambda _i, column: f"={get_column_letter(column)}7*{get_column_letter(column)}5", total=True)
    write_row(9, lambda _i, _column: "=1", percent=True)
    write_row(10, lambda _i, column: f"={get_column_letter(column)}8*{get_column_letter(column)}9", total=True)
    write_row(11, lambda _i, column: src("energy", column), total=True)
    write_row(12, lambda _i, column: f"={get_column_letter(column)}11", total=True)
    write_row(13, lambda _i, _column: "=1", percent=True)
    write_row(14, lambda _i, column: f"={get_column_letter(column)}12*{get_column_letter(column)}13", total=True)
    write_row(15, lambda _i, column: src("subsidy", column), total=True)
    write_row(16, lambda _i, column: f"={get_column_letter(column)}15", total=True)
    write_row(17, lambda _i, _column: "=1", percent=True)
    write_row(18, lambda _i, column: f"={get_column_letter(column)}16*{get_column_letter(column)}17", total=True)
    write_row(19, lambda _i, column: src("primary", column), total=True)
    write_row(20, lambda _i, column: f"={get_column_letter(column)}19", total=True)
    write_row(21, lambda _i, _column: "=1", percent=True)
    write_row(22, lambda _i, column: f"={get_column_letter(column)}20*{get_column_letter(column)}21", total=True)
    write_row(23, lambda _i, column: src("secondary", column), total=True)
    write_row(24, lambda _i, column: f"={get_column_letter(column)}23", total=True)
    write_row(25, lambda _i, _column: "=1", percent=True)
    write_row(26, lambda _i, column: f"={get_column_letter(column)}24*{get_column_letter(column)}25", total=True)
    write_row(27, lambda _i, column: f"=SUM({get_column_letter(column)}10,{get_column_letter(column)}14,{get_column_letter(column)}18,{get_column_letter(column)}22,{get_column_letter(column)}26)", total=True)
    write_row(28, lambda _i, column: f"={get_column_letter(column)}27/(1+{parameter_ref('vat_rate')})", total=True)
    write_row(29, lambda _i, column: src("depreciation", column), total=True)
    write_row(30, lambda _i, column: f"=SUM($D29:{get_column_letter(column)}29)", total=True)
    write_row(31, lambda year_index, column: "=0" if year_index == 0 else f"=MAX('项目概览'!$B$10/10000-{get_column_letter(column)}30,0)")
    write_row(32, lambda _i, _column: "=0")
    write_row(33, lambda year_index, _column: "=0" if year_index == 0 else f"={parameter_ref('land_rent_yuan')}/10000", total=True)
    write_row(35, lambda year_index, column: "=0" if year_index == 0 else amount_from_cashflow(column, "AA"), total=True)
    write_row(36, lambda year_index, _column: "=0" if year_index == 0 else f"={parameter_ref('fixed_operation_cost_yuan')}/10000", total=True)
    write_row(37, lambda year_index, column: "=0" if year_index == 0 else amount_from_cashflow(column, "Z"), total=True)
    write_row(38, lambda year_index, _column: "=0" if year_index == 0 else f"={parameter_ref('other_operating_cost_yuan')}/10000", total=True)
    write_row(34, lambda year_index, column: "=0" if year_index == 0 else f"={src('operating_cost', column)[1:]}-{get_column_letter(column)}33-{get_column_letter(column)}35-{get_column_letter(column)}36-{get_column_letter(column)}37-{get_column_letter(column)}38")
    write_row(39, lambda _i, column: src("replacement", column), total=True)
    write_row(40, lambda _i, column: f"=SUM({get_column_letter(column)}33:{get_column_letter(column)}39)", total=True)
    write_row(41, lambda year_index, column: "='项目概览'!$B$10*" + parameter_ref("loan_ratio") + "/10000" if year_index == 0 else f"={get_column_letter(column - 1)}41-{get_column_letter(column)}43")
    write_row(42, lambda year_index, column: "='项目概览'!$B$11/10000" if year_index == 0 else src("interest", column), total=True)
    write_row(43, lambda year_index, column: "=0" if year_index == 0 else src("principal", column), total=True)
    write_row(44, lambda _i, column: f"=SUM({get_column_letter(column)}42:{get_column_letter(column)}43)", total=True)
    write_row(45, lambda _i, column: src("output_vat", column), total=True)
    write_row(46, lambda _i, column: f"={src('credit_closing', column)[1:]}+{src('credit_used', column)[1:]}", total=True)
    write_row(47, lambda _i, column: src("credit_used", column), total=True)
    write_row(48, lambda _i, column: src("actual_vat", column), total=True)
    write_row(49, lambda _i, column: src("vat_surcharge", column), total=True)
    write_row(50, lambda _i, column: src("stamp_tax", column), total=True)
    write_row(51, lambda _i, column: amount_from_cashflow(column, "P"), total=True)
    write_row(52, lambda _i, column: src("income_tax", column), total=True)
    write_row(53, lambda _i, column: amount_from_cashflow(column, "Q"), total=True)
    write_row(55, lambda _i, column: f"={get_column_letter(column)}27", total=True)
    write_row(57, lambda _i, column: f"={get_column_letter(column)}40", total=True)
    write_row(58, lambda _i, column: f"={get_column_letter(column)}44", total=True)
    write_row(59, lambda _i, column: f"={get_column_letter(column)}48", total=True)
    write_row(60, lambda _i, column: f"={get_column_letter(column)}49", total=True)
    write_row(61, lambda _i, column: f"={get_column_letter(column)}50", total=True)
    write_row(62, lambda _i, column: f"={get_column_letter(column)}52", total=True)
    write_row(56, lambda _i, column: f"=SUM({get_column_letter(column)}57:{get_column_letter(column)}62)", total=True)
    write_row(63, lambda _i, column: src("equity_cashflow", column), total=True)
    write_row(64, lambda _i, column: src("cumulative_equity", column), total=True)
    write_row(69, lambda _i, column: f"={get_column_letter(column)}27", total=True)
    write_row(71, lambda _i, column: f"={get_column_letter(column)}40", total=True)
    write_row(72, lambda _i, column: f"={get_column_letter(column)}48", total=True)
    write_row(73, lambda _i, column: f"={get_column_letter(column)}52", total=True)
    write_row(74, lambda _i, column: f"={get_column_letter(column)}49", total=True)
    write_row(75, lambda _i, column: f"={get_column_letter(column)}50", total=True)
    write_row(70, lambda _i, column: f"=SUM({get_column_letter(column)}71:{get_column_letter(column)}75)", total=True)
    write_row(76, lambda _i, column: src("project_cashflow", column), total=True)
    write_row(77, lambda _i, column: src("cumulative_project", column), total=True)
    for row, cashflow_row in ((65, 63), (78, 76)):
        set_year(row, 4, f"=IRR(D{cashflow_row}:{last_year_letter}{cashflow_row})", percent=True)
    discount = parameter_ref("discount_rate")
    set_year(66, 4, f"=NPV({discount},E63:{last_year_letter}63)+D63")
    set_year(79, 4, f"=NPV({discount},E76:{last_year_letter}76)+D76")
    set_year(67, 4, "='项目概览'!$B$15")
    set_year(80, 4, "='项目概览'!$B$15")
    sheet.cell(81, 1, "说明：服务器版复现原始模板结构和可重算公式；宏、数据表和数组公式保持为明确差异。")
    sheet.cell(81, 1).font = Font(name="Microsoft YaHei", size=9, color="7F6000", italic=True)
    sheet.cell(81, 1).fill = PatternFill("solid", fgColor=TEMPLATE_SECTION)
    sheet.cell(81, 1).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    sheet.merge_cells(start_row=81, start_column=1, end_row=81, end_column=6)
    sheet.auto_filter.ref = f"A2:{total_letter}80"


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
    if sheet.title == "财务模板":
        sheet.column_dimensions["A"].width = 18
        sheet.column_dimensions["B"].width = 7
        sheet.column_dimensions["C"].width = 28
        for column in range(4, sheet.max_column + 1):
            sheet.column_dimensions[get_column_letter(column)].width = 12
        return
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
