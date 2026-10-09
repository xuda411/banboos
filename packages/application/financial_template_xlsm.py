"""Export a financial result into a copy of the 1.6.6 Excel template.

The original template is treated as a read-only asset.  This adapter only
changes the copied workbook's input cells and appends a small Banboos snapshot
sheet, so the customer's macros, formulas and print layout remain available
for Excel/WPS recalculation.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from packages.application.financial_xlsm_review import write_native_review
from packages.contracts.financial import FinancialTaskParameters


def financial_template_path(configured: str | Path | None = None) -> Path | None:
    """Resolve the configured 1.6.6 template, including the bundled local copy."""
    value = configured or os.getenv("BANBOOS2_FINANCIAL_TEMPLATE")
    candidate = Path(value).expanduser() if value else (
        Path(__file__).resolve().parents[2] / "var" / "templates" / "独立储能项目经济性测算工具.xlsm"
    )
    return candidate.resolve() if candidate.is_file() and candidate.suffix.lower() == ".xlsm" else None


def validated_template_parameters(result: dict) -> dict:
    """Do not silently fill incomplete historical task snapshots with defaults."""
    inputs = result.get("input_parameters") or {}
    required = set(FinancialTaskParameters.model_fields) - {
        "replace_year", "source_run_id", "auxiliary_annual_cycles",
    }
    if required - inputs.keys():
        raise ValueError("任务参数快照不完整，请重新测算后导出原版模板")
    p = FinancialTaskParameters.model_validate(inputs).model_dump()
    if p["auxiliary_annual_cycles"]:
        raise ValueError("原版模板尚未映射辅助服务等效循环，请导出标准 XLSX（包含完整参数与寿命公式）")
    if p["operation_years"] > 25:
        raise ValueError("原版模板仅覆盖 25 个运营年度，超过 25 年请导出标准 XLSX")
    if p["revenue_phases"]:
        raise ValueError("原版模板尚不支持服务器分阶段收益规则，请导出标准 XLSX")
    if p["annual_revenue_yuan"] is None:
        raise ValueError("任务尚未解析节点收益，请完成测算后再导出")
    if len(result.get("yearly", [])) != p["operation_years"]:
        raise ValueError("任务年度结果不完整，请重新测算")
    return p


def template_input_values(result: dict) -> dict[str, object]:
    """Return the editable cells and values used by the 1.6.6 template.

    Values use the template's native units: amounts in the parameter sheet are
    万元, while the server model keeps monetary values in 元.
    """
    p = result.get("input_parameters") or {}
    capacity = float(p.get("capacity_mwh") or result.get("capacity_mwh") or 0)
    replacement_unit = (
        float(p.get("replace_capex_yuan") or 0) / (capacity * 1_000_000)
        if capacity
        else 0
    )
    return {
        "D3": p.get("power_mw", result.get("power_mw")),
        "D4": p.get("capacity_mwh", result.get("capacity_mwh")),
        "D5": p.get("single_side_efficiency"),
        "D6": p.get("dod"),
        "D8": p.get("final_eol"),
        "D10": p.get("cycle_life_cycles"),
        "D11": p.get("first_year_eol"),
        "D16": p.get("construction_years"),
        "D27": p.get("operation_years"),
        "D28": (float(p.get("land_rent_yuan") or 0) / 10_000),
        "D29": p.get("om_rate"),
        "D31": p.get("om_growth"),
        "D32": p.get("insurance_rate"),
        "D34": (float(p.get("fixed_operation_cost_yuan") or 0) / 10_000),
        "D35": (float(p.get("revenue_share_threshold_yuan") or 0) / 10_000),
        "D36": p.get("revenue_share_rate"),
        "D37": (float(p.get("other_operating_cost_yuan") or 0) / 10_000),
        "D38": "是" if p.get("replace_year") else "否",
        "D39": p.get("replace_year") or 0,
        "D40": replacement_unit,
        "D42": p.get("residual_rate"),
        "D43": p.get("loan_years"),
        "D44": p.get("loan_ratio"),
        "D45": p.get("loan_rate"),
        "D47": "融资" if float(p.get("loan_ratio") or 0) else "不融资",
        "D48": p.get("construction_loan_rate") if p.get("loan_ratio") else 0,
        "D49": p.get("discount_rate"),
        # These three cells are formulas in the source template.  They are
        # replaced with the server's traceable annual inputs so the copied
        # statement starts from the same price/fee assumptions as the run.
        "D50": float(p.get("capacity_fee_yuan") or 0) / 10_000,
        "D51": float(p.get("annual_revenue_yuan") or 0) / 10_000,
        "D52": float(p.get("secondary_frequency_yuan") or 0) / 10_000,
        "D55": p.get("vat_rate"),
        "D56": p.get("income_tax_rate"),
        "D57": p.get("input_vat_rate_equipment"),
        "D58": p.get("input_vat_rate_other"),
    }


def template_sheet_values(result: dict) -> dict[str, dict]:
    """Map the actual upstream cells used by the native financial statement.

    Server inputs are annual aggregates, not a tariff/ancillary-service market
    model. Unknown price, land and service assumptions are cleared, and the
    supplied annual amounts override the corresponding intermediate totals.
    All overrides are listed in the review sheet.
    """
    p = validated_template_parameters(result)
    parameters = template_input_values(result)
    parameters.update({"D12": 0, "D13": 0, "D15": 0, "K23": 0,
                       "I33": 0, "I34": 0, "I35": 0, "K2": "项目地区未设置",
                       "D18": "=D22*D44*D48*D16"})
    # No detailed EPC allocation exists in the server contract. Show the two
    # supplied tax categories instead of reusing the template's sample prices.
    parameters.update({f"L{row}": 0 for row in range(12, 22)})
    parameters["L12"] = p["capex_yuan_per_wh"] * p["equipment_investment_share"]
    parameters["L14"] = p["capex_yuan_per_wh"] * (1 - p["equipment_investment_share"])
    parameters.update({"I12": "设备投资汇总", "J12": "未提供明细",
                       "J14": "其他投资汇总"})
    # In the frozen desktop workbook D24/D47 are the year-one energy base;
    # the annual EOL factor is then applied again by 财务指标!E12/E14.  Keep
    # the compatibility mode explicit so normal server exports retain their
    # raw annual aggregate semantics.
    energy = p["annual_revenue_yuan"] / 10000
    if p["eol_method"] in {"desktop_template", "native_xlsm"}:
        energy *= p["first_year_eol"]
    mappings = {
        "参数设定 ": parameters,
        "容量类": {"D12": 0, "D13": 0, "D14": p["capacity_lease_yuan"] / 10000,
                  "D15": p["operation_years"], "D16": "延续", "D18": "否",
                  "D19": 0, "D20": "否", "D22": 0, "D23": 0,
                  "D25": p["capacity_fee_yuan"] / 10000,
                  "D26": p["operation_years"], "D29": 0, "D30": 0,
                  "D31": "是", "D32": 0},
        "电量类 ": {"D11": p["first_year_eol"], "D12": "否", "D15": p["annual_cycles"],
                   "D17": 0, "D19": 0, "D22": "是", "D23": p["operation_years"],
                   "D24": energy, "D25": 0, "D27": "有" if p["subsidy_yuan"] else "无",
                   "D28": 0, "D31": p["subsidy_yuan"] / 10000, "D32": "是",
                   "D33": p["operation_years"], "D34": 0, "D36": "否",
                   "D39": p["annual_cycles"], "D41": 0, "D43": 0,
                   "D46": "是", "D47": energy, "D48": 0},
        "辅助服务类": {"D12": "是" if p["primary_frequency_yuan"] else "否",
                      "D13": 0, "D15": 0, "D16": 0, "D17": 0, "D18": 0,
                      "D19": p["primary_frequency_yuan"] / 10000,
                      "D21": 0, "D23": 0, "D25": 0, "D26": "否",
                      "D29": 0, "D30": "是" if p["secondary_frequency_yuan"] else "否",
                      "D31": 0, "D33": 0, "D34": 0, "D35": 0, "D36": 0,
                      "D37": p["secondary_frequency_yuan"] / 10000,
                      "D39": 0, "D41": 0, "D43": 0, "D44": "否", "D47": 0},
    }
    if p["eol_method"] in {"desktop_template", "native_xlsm"}:
        mappings["EOL"] = _desktop_template_eol_values(p)
    return mappings


def _desktop_template_eol_values(parameters: dict) -> dict[str, float]:
    """Map the explicit desktop calendar/cycle curves into the native EOL tab."""
    table = list(parameters.get("calendar_eol_table") or ())
    if not table:
        table = [1.0] + [max(0.0, 1.0 - 0.005 * index) for index in range(1, 31)]
    values: dict[str, float] = {}
    for index in range(31):
        if index < len(table):
            calendar = float(table[index])
        else:
            calendar = max(0.0, float(table[-1]) - 0.005 * (index - len(table) + 1))
        cycle = 1.0 if index == 0 else 0.99 if index == 1 else 0.98 - 0.015 * (index - 2) - 0.0075
        column = get_column_letter(index + 3)  # C:AG, including curve year zero.
        values[f"{column}3"] = calendar
        values[f"{column}4"] = cycle
        # The native workbook applies the row-9 midpoint curve to annual
        # revenue.  Writing the combined curve explicitly avoids silently
        # falling back to the template's sample formulas when the server
        # supplies a desktop_template run.  Rows 5 and 8 are kept in sync so
        # both the replacement and non-replacement branches use the same
        # curve after Excel recalculation.
        combined = min(calendar, cycle)
        values[f"{column}5"] = combined
        values[f"{column}9"] = combined
        values[f"{column}8"] = combined
    return values


def export_financial_xlsm(
    result: dict,
    destination: str | Path,
    template: str | Path | None = None,
) -> Path:
    """Create a macro-enabled workbook from a read-only template copy."""
    source = financial_template_path(template)
    if source is None:
        configured = template or os.getenv("BANBOOS2_FINANCIAL_TEMPLATE")
        if configured:
            raise FileNotFoundError(f"财务 XLSM 模板不存在或格式错误: {Path(configured).expanduser()}")
        raise ValueError("未配置财务 XLSM 模板，且项目 var/templates 下没有默认模板")

    target = Path(destination).expanduser().resolve()
    if target == source or (target.exists() and target.samefile(source)):
        raise ValueError("导出目标不能覆盖源模板")
    if target.suffix.lower() != ".xlsm":
        raise ValueError("原版模板导出目标必须是 .xlsm 文件")
    mappings = template_sheet_values(result)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{target.stem}-", suffix=".xlsm",
                                     dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    workbook = None
    try:
        # Copy first, then edit the copy.  The source template is never opened
        # for writing and is therefore safe to reuse across concurrent runs.
        shutil.copyfile(source, temporary)
        workbook = load_workbook(temporary, data_only=False, keep_vba=True)
        workbook.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True,
                                              forceFullCalc=True)
        required_sheets = {*mappings, "财务指标", "EOL", "收益浮动系数"}
        if required_sheets - set(workbook.sheetnames):
            raise ValueError("财务模板结构不匹配：缺少 1.6.6 必需工作表")
        if (workbook["参数设定 "]["C3"].value != "系统功率（MW）"
                or workbook["财务指标"]["C76"].value != "现金净流入(万元)"):
            raise ValueError("财务模板版本不匹配：关键单元格定义已变化")
        edits = []
        for sheet_name, values in mappings.items():
            for cell, value in values.items():
                previous = workbook[sheet_name][cell].value
                edits.append((sheet_name, cell, previous, value))
                workbook[sheet_name][cell] = value
        _write_snapshot_sheet(workbook, result, source)
        write_native_review(workbook, result, edits)
        workbook.active = workbook.sheetnames.index("Banboos2.0快照")
        workbook.save(temporary)
        workbook.close()
        if workbook.vba_archive is not None:
            workbook.vba_archive.close()
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if workbook is not None:
            workbook.close()
            if workbook.vba_archive is not None:
                workbook.vba_archive.close()
    return target


def _write_snapshot_sheet(workbook, result: dict, source: Path) -> None:
    name = "Banboos2.0快照"
    if name in workbook.sheetnames:
        del workbook[name]
    sheet = workbook.create_sheet(name)
    sheet.sheet_view.showGridLines = False
    sheet["A1"] = "Banboos 2.0 · 服务器测算快照"
    sheet["A1"].font = Font(name="Microsoft YaHei", size=16, bold=True, color="173B35")
    sheet.merge_cells("A1:D1")
    sheet["A2"] = "原版规则对照稿。请查看“原版对账”；模板计算结果尚未通过服务器等价验收。"
    sheet.row_dimensions[2].height = 42
    sheet["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    sheet.merge_cells("A2:D2")
    sheet["A2"].font = Font(name="Microsoft YaHei", italic=True, color="5B756E")
    rows = [
        ("来源模板", source.name),
        ("任务 ID", result.get("run_id") or ""),
        ("模型版本", result.get("model_version") or ""),
        ("额定功率（MW）", result.get("power_mw")),
        ("额定容量（MWh）", result.get("capacity_mwh")),
        ("全投资 IRR", result.get("full_irr")),
        ("全投资 NPV（元）", result.get("full_npv_yuan")),
        ("资本金 IRR", result.get("equity_irr")),
        ("资本金 NPV（元）", result.get("equity_npv_yuan")),
    ]
    for row, (label, value) in enumerate(rows, start=4):
        sheet.cell(row, 1, label)
        sheet.cell(row, 2, value)
        sheet.cell(row, 1).fill = PatternFill("solid", fgColor="E8F2EE")
        sheet.cell(row, 1).font = Font(name="Microsoft YaHei", bold=True, color="173B35")
        sheet.cell(row, 2).font = Font(name="Microsoft YaHei", color="173B35")
        sheet.cell(row, 1).alignment = Alignment(vertical="center")
        sheet.cell(row, 2).alignment = Alignment(vertical="center")
        if "IRR" in label:
            sheet.cell(row, 2).number_format = "0.00%"
    for column, width in {"A": 24, "B": 60, "C": 14, "D": 14}.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A4"
    sheet.print_area = "A1:D12"
