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
from openpyxl.workbook.properties import CalcProperties

DEFAULT_TEMPLATE = Path(
    r"C:\Users\Laptop\Desktop\晔旭辉能源测算工具\独立储能项目经济性测算工具.xlsm"
)


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
        "D48": p.get("construction_loan_rate"),
        "D49": p.get("discount_rate"),
        # These three cells are formulas in the source template.  They are
        # replaced with the server's traceable annual inputs so the copied
        # statement starts from the same price/fee assumptions as the run.
        "D50": float(p.get("capacity_fee_yuan") or 0) / 10_000
        + float(p.get("capacity_lease_yuan") or 0) / 10_000,
        "D51": float(p.get("annual_revenue_yuan") or 0) / 10_000,
        "D52": (float(p.get("primary_frequency_yuan") or 0)
                + float(p.get("secondary_frequency_yuan") or 0)) / 10_000,
        "D55": p.get("vat_rate"),
        "D56": p.get("income_tax_rate"),
        "D57": p.get("input_vat_rate_equipment"),
        "D58": p.get("input_vat_rate_other"),
    }


def export_financial_xlsm(
    result: dict,
    destination: str | Path,
    template: str | Path | None = None,
) -> Path:
    """Create a macro-enabled workbook from a read-only template copy."""
    source = Path(template or os.getenv("BANBOOS2_FINANCIAL_TEMPLATE", DEFAULT_TEMPLATE))
    if not source.exists():
        raise FileNotFoundError(f"财务 XLSM 模板不存在: {source}")
    if source.suffix.lower() != ".xlsm":
        raise ValueError("财务模板必须是 .xlsm 文件")

    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{target.stem}-", suffix=".xlsm",
                                     dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        # Copy first, then edit the copy.  The source template is never opened
        # for writing and is therefore safe to reuse across concurrent runs.
        shutil.copyfile(source, temporary)
        workbook = load_workbook(temporary, data_only=False, keep_vba=True)
        workbook.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True,
                                              forceFullCalc=True)
        sheet_name = next((name for name in workbook.sheetnames if name.strip() == "参数设定"), None)
        if sheet_name is None:
            raise ValueError("财务 XLSM 模板缺少“参数设定”工作表")
        parameter_sheet = workbook[sheet_name]
        for cell, value in template_input_values(result).items():
            if value is not None:
                parameter_sheet[cell] = value
        _write_snapshot_sheet(workbook, result, source)
        workbook.save(temporary)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
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
    sheet["A2"] = "本页用于追溯服务器结果；模板原生公式和宏请在 Excel/WPS 中重新计算。"
    sheet.merge_cells("A2:D2")
    sheet["A2"].font = Font(name="Microsoft YaHei", italic=True, color="5B756E")
    rows = [
        ("来源模板", str(source)),
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
    for column, width in {"A": 24, "B": 60, "C": 14, "D": 14}.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A4"
    sheet.print_area = "A1:D12"
