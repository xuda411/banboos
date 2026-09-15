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
    registry.complete(upstream.run_id, result={"annualized_net_revenue_yuan": 6_000_000,
                                             "power_mw": 50, "capacity_mwh": 200})
    item = registry.submit("financial", parameters={
        "power_mw": 50, "capacity_mwh": 200, "source_run_id": upstream.run_id,
    })
    assert run_once(registry)
    result = registry.get(item.run_id)
    assert result.status == "succeeded"
    assert result.result["duration_hours"] == 4
    assert result.result["source_run_id"] == upstream.run_id


def test_financial_source_supports_price_baseline_and_rejects_scale_mismatch():
    registry = RunRegistry()
    upstream = registry.submit("price-analysis")
    registry.claim_next(timeout=0)
    registry.complete(upstream.run_id, result={"annualized_revenue_yuan": 8_000_000,
                                             "power_mw": 100, "capacity_mwh": 200})
    matching = registry.submit("financial", parameters={
        "power_mw": 100, "capacity_mwh": 200, "source_run_id": upstream.run_id})
    run_once(registry)
    assert registry.get(matching.run_id).result["input_parameters"]["annual_revenue_yuan"] == 8_000_000
    mismatch = registry.submit("financial", parameters={
        "power_mw": 50, "capacity_mwh": 200, "source_run_id": upstream.run_id})
    run_once(registry)
    assert registry.get(mismatch.run_id).status == "failed"
    assert "规模一致" in registry.get(mismatch.run_id).message


def test_financial_model_rejects_invalid_ratio_inputs():
    with pytest.raises(ValueError):
        FinancialTaskParameters(power_mw=0, capacity_mwh=200, annual_revenue_yuan=1)
    with pytest.raises(ValueError):
        calculate_financials(FinancialTaskParameters(power_mw=100, capacity_mwh=200,
                                                     annual_revenue_yuan=1,
                                                     discount_rate=-1).financial())
    with pytest.raises(ValueError, match="时长"):
        FinancialTaskParameters(power_mw=100, capacity_mwh=10, annual_revenue_yuan=1)
    with pytest.raises(ValueError, match="时长"):
        FinancialTaskParameters(power_mw=1, capacity_mwh=30, annual_revenue_yuan=1)


def test_sensitivity_task_reuses_financial_model_for_each_scenario():
    registry = RunRegistry()
    item = registry.submit("sensitivity", parameters={
        "base": {"power_mw": 100, "capacity_mwh": 200, "annual_revenue_yuan": 8_000_000},
        "variable": "annual_revenue_yuan", "change_rates": [-0.2, 0, 0.2],
    })
    assert run_once(registry)
    result = registry.get(item.run_id)
    assert result.status == "succeeded"
    assert len(result.result["points"]) == 3
    assert result.result["points"][0]["full_npv_yuan"] < result.result["points"][-1]["full_npv_yuan"]
