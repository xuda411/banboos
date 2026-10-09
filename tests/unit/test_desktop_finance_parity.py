import pytest

from packages.contracts.financial import FinancialTaskParameters
from packages.domain.financial_model import calculate_financials

REVENUE = (520 * 0.92 - 50 / 0.92) * 120 * 0.95 * 350


@pytest.mark.parametrize(
    ("loan_ratio", "full_npv", "cashflow_year_7"),
    [
        (0.0, -22_679_834.744505547, 9_326_641.640005728),
        (0.7, -19_335_028.061976746, 9_929_848.231290132),
    ],
)
def test_desktop_template_finance_fixed_cases(loan_ratio, full_npv, cashflow_year_7):
    """Lock the independent 1.6.6 financial baseline used by parity runs."""
    parameters = FinancialTaskParameters(
        power_mw=60,
        capacity_mwh=120,
        annual_revenue_yuan=REVENUE,
        loan_ratio=loan_ratio,
        discount_rate=0.04,
        eol_method="desktop_template",
        insurance_rate=0.002,
        fixed_operation_cost_yuan=2_000_000,
        replace_year=11,
        replace_capex_yuan=36_000_000,
        vat_rate=0.13,
        equipment_investment_share=0.0,
    )
    result = calculate_financials(parameters.financial())
    assert result["full_npv_yuan"] == pytest.approx(full_npv, abs=0.01)
    assert result["cashflows_yuan"][7] == pytest.approx(cashflow_year_7, abs=0.01)
    assert result["yearly"][0]["revenue_yuan"] == pytest.approx(16_247_970.374086956, abs=0.01)


def test_native_xlsm_finance_matches_recalculated_template_case():
    """The opt-in native mode mirrors the frozen XLSM formula semantics."""
    parameters = FinancialTaskParameters(
        power_mw=60,
        capacity_mwh=120,
        annual_revenue_yuan=REVENUE,
        loan_ratio=.7,
        discount_rate=.04,
        eol_method="native_xlsm",
        insurance_rate=.002,
        fixed_operation_cost_yuan=2_000_000,
        replace_year=11,
        replace_capex_yuan=36_000_000,
        vat_rate=.13,
        equipment_investment_share=0.0,
    )
    result = calculate_financials(parameters.financial())
    assert result["full_irr"] == pytest.approx(0.033883826497549174, abs=1e-12)
    assert result["full_npv_yuan"] == pytest.approx(-8_593_605.30590737, abs=0.01)
    assert result["yearly"][0]["project_cashflow_yuan"] == pytest.approx(12_739_829.970754176, abs=0.01)
    assert result["yearly"][0]["equity_cashflow_yuan"] == pytest.approx(-2_107_667.6602394525, abs=0.01)
    assert result["yearly"][10]["depreciation_yuan"] == pytest.approx(8_162_155.008, abs=0.01)
