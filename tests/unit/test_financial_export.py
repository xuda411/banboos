from openpyxl import load_workbook

from packages.application.financial_export import export_financial_xlsx
from packages.contracts.financial import FinancialTaskParameters
from packages.domain.financial_model import calculate_financials


def test_financial_export_has_typed_sheets_and_frozen_headers(tmp_path):
    result = calculate_financials(FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=8_000_000,
    ).financial())
    result["source_run_id"] = "demo-run"
    destination = export_financial_xlsx(result, tmp_path / "financial.xlsx")
    workbook = load_workbook(destination, data_only=False)
    assert workbook.sheetnames == ["项目概览", "年度现金流", "融资明细"]
    assert workbook["年度现金流"].freeze_panes == "A4"
    assert workbook["年度现金流"]["C5"].value == result["yearly"][0]["energy_revenue_yuan"]
    assert workbook["项目概览"]["B12"].value == result["total_investment_yuan"]
