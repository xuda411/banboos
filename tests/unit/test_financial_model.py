import pytest

from apps.worker.main import run_once
from packages.application.run_registry import RunRegistry
from packages.contracts.financial import FinancialTaskParameters
from packages.domain.financial_model import calculate_financials


def test_financial_model_returns_cashflows_and_ratio_duration():
    parameters = FinancialTaskParameters(power_mw=100, capacity_mwh=200,
                                         annual_revenue_yuan=8_000_000)
    result = calculate_financials(parameters.financial())
    assert result["duration_hours"] == 2
    assert len(result["yearly"]) == 25
    assert len(result["cashflows_yuan"]) == 26
    assert result["initial_investment_yuan"] == pytest.approx(240_000_000)


def test_financial_model_breaks_out_revenues_and_financing():
    parameters = FinancialTaskParameters(
        power_mw=50, capacity_mwh=200, annual_revenue_yuan=6_000_000,
        capacity_lease_yuan=500_000, subsidy_yuan=200_000,
        loan_ratio=0.8, loan_years=10, replace_year=3, replace_capex_yuan=20_000_000,
    )
    result = calculate_financials(parameters.financial())
    first, replacement_year = result["yearly"][0], result["yearly"][2]
    assert first["capacity_lease_yuan"] == 500_000
    assert first["loan_principal_yuan"] > 0
    assert replacement_year["replacement_capex_yuan"] == 20_000_000
    assert len(result["equity_cashflows_yuan"]) == 26


def test_financial_task_is_traceable_to_upstream_run():
    registry = RunRegistry()
    upstream = registry.submit("strict-dispatch")
    assert registry.claim_next(timeout=0)
    registry.complete(upstream.run_id, result={"annualized_net_revenue_yuan": 6_000_000})
    item = registry.submit("financial", parameters={
        "power_mw": 50, "capacity_mwh": 200, "source_run_id": upstream.run_id,
    })
    assert run_once(registry)
    result = registry.get(item.run_id)
    assert result.status == "succeeded"
    assert result.result["duration_hours"] == 4
    assert result.result["source_run_id"] == upstream.run_id


def test_financial_model_rejects_invalid_ratio_inputs():
    with pytest.raises(ValueError):
        FinancialTaskParameters(power_mw=0, capacity_mwh=200, annual_revenue_yuan=1)
    with pytest.raises(ValueError):
        calculate_financials(FinancialTaskParameters(power_mw=100, capacity_mwh=200,
                                                     annual_revenue_yuan=1,
                                                     discount_rate=-1).financial())
