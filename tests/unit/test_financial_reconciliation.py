from packages.contracts.financial import FinancialTaskParameters
from packages.domain.financial_model import calculate_financials
from packages.domain.financial_reconciliation import reconcile_financial


def test_financial_reconciliation_matches_model_cashflows():
    parameters = FinancialTaskParameters(power_mw=100, capacity_mwh=200,
                                         annual_revenue_yuan=8_000_000, operation_years=3,
                                         loan_ratio=0.8, construction_years=0.5)
    result = calculate_financials(parameters.financial())
    report = reconcile_financial(result, parameters.model_dump())
    assert report["status"] == "passed"
    assert len(report["checks"]) == 13


def test_financial_reconciliation_detects_changed_npv():
    parameters = FinancialTaskParameters(power_mw=50, capacity_mwh=200,
                                         annual_revenue_yuan=6_000_000, operation_years=2)
    result = calculate_financials(parameters.financial())
    result["full_npv_yuan"] += 10
    report = reconcile_financial(result, parameters.model_dump())
    assert report["status"] == "failed"
    assert any(check["name"] == "project_npv" and check["status"] == "failed"
               for check in report["checks"])
