from openpyxl import load_workbook

from packages.application.financial_export import export_financial_xlsx
from packages.contracts.financial import FinancialTaskParameters
from packages.domain.financial_model import calculate_financials


def test_financial_export_has_typed_sheets_and_frozen_headers(tmp_path):
    result = calculate_financials(FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=8_000_000,
    ).financial())
    result["source_run_id"] = "demo-run"
    result["input_parameters"] = {"power_mw": 100, "capacity_mwh": 200, "annual_revenue_yuan": 8_000_000}
    destination = export_financial_xlsx(result, tmp_path / "financial.xlsx")
    workbook = load_workbook(destination, data_only=False)
    assert workbook.sheetnames == ["项目概览", "测算参数", "年度现金流", "融资明细", "全周期现金流", "模板映射"]
    assert workbook["测算参数"]["B5"].value == 100
    assert workbook["年度现金流"].freeze_panes == "B5"
    assert workbook["年度现金流"]["C5"].value == result["yearly"][0]["energy_revenue_yuan"]
    assert workbook["年度现金流"]["U4"].value == "实际应缴增值税（元）"
    assert workbook["年度现金流"]["AB4"].value == "项目税前现金流（元）"
    assert workbook["项目概览"]["B12"].value == result["total_investment_yuan"]


def test_formula_audit_uses_task_inputs_and_preserves_snapshot(tmp_path):
    parameters = FinancialTaskParameters(power_mw=30, capacity_mwh=120,
        annual_revenue_yuan=20_000_000, loan_ratio=.7, replace_year=3,
        replace_capex_yuan=8_000_000)
    result = calculate_financials(parameters.financial())
    result["input_parameters"] = parameters.model_dump(exclude_none=True)
    path = export_financial_xlsx(result, tmp_path / "audit.xlsx")
    workbook = load_workbook(path)
    audit = workbook["公式复核"]
    assert audit["C5"].data_type == "f"
    assert "测算参数" in audit["C5"].value
    assert audit["M5"].value == "=C5-D5-F5-G5-H5-K5"
    assert audit["O29"].value == "=M29-'年度现金流'!O29"
    assert workbook["年度现金流"]["O5"].value == result["yearly"][0]["equity_cashflow_yuan"]
    assert "年限变更" in audit["A2"].value
    result["model_version"] = "banboos-financial-1.0.0"
    old = load_workbook(export_financial_xlsx(result, tmp_path / "old.xlsx"))
    assert "公式复核" not in old.sheetnames


def test_formula_audit_includes_template_cost_and_tax_drivers(tmp_path):
    parameters = FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=12_000_000,
        insurance_rate=0.002, fixed_operation_cost_yuan=100_000,
        revenue_share_threshold_yuan=5_000_000, revenue_share_rate=0.3,
        vat_rate=0.13, stamp_tax_rate=0.0005,
        eol_method="calendar_cycle_min",
    )
    result = calculate_financials(parameters.financial())
    result["input_parameters"] = parameters.model_dump(exclude_none=True)
    workbook = load_workbook(export_financial_xlsx(result, tmp_path / "template-parity.xlsx"))
    audit = workbook["公式复核"]
    assert "MAX(0" in audit["J5"].value
    assert "B5" in audit["D5"].value
    assert audit["B5"].value.startswith("=IF(")
    assert "Q5" in audit["P5"].value
    assert audit["S5"].value.startswith("=(C5-")
