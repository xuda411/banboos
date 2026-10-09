import pytest

from apps.worker.main import run_once
from packages.application.run_registry import RunRegistry
from packages.contracts.financial import FinancialTaskParameters
from packages.domain.financial_model import calculate_financials


def test_unlevered_equity_cashflow_equals_project_cashflow():
    result = calculate_financials(FinancialTaskParameters(
        power_mw=60, capacity_mwh=120, annual_revenue_yuan=25_000_000,
        replace_year=3, replace_capex_yuan=4_000_000,
    ).financial())
    assert result["equity_cashflows_yuan"] == pytest.approx(result["cashflows_yuan"])
    assert result["equity_irr"] == pytest.approx(result["full_irr"])


def test_levered_cashflow_does_not_add_back_depreciation_twice():
    result = calculate_financials(FinancialTaskParameters(
        power_mw=1, capacity_mwh=2, annual_revenue_yuan=1_000_000,
        capex_yuan_per_wh=1, operation_years=2, first_year_eol=1, final_eol=1,
        om_rate=0, loan_ratio=.5, loan_years=2, loan_rate=.1,
        construction_years=0, residual_rate=0, income_tax_rate=.25,
    ).financial())
    # Year 1: 1m revenue - 100k interest - 500k principal; no taxable profit.
    assert result["equity_cashflows_yuan"] == pytest.approx([-1_000_000, 400_000, 450_000])


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


def test_financial_model_supports_template_operating_costs_and_indirect_tax():
    parameters = FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=12_000_000,
        insurance_rate=0.002, fixed_operation_cost_yuan=100_000,
        revenue_share_threshold_yuan=5_000_000, revenue_share_rate=0.3,
        vat_rate=0.13, stamp_tax_rate=0.0005,
        eol_method="calendar_cycle_min", annual_cycles=350, cycle_life_cycles=8_000,
    )
    result = calculate_financials(parameters.financial())
    first = result["yearly"][0]
    assert first["output_vat_yuan"] > 0
    assert first["insurance_yuan"] > 0
    assert first["revenue_share_yuan"] > 0
    assert first["net_revenue_yuan"] < first["gross_revenue_yuan"]
    assert first["eol"] <= parameters.first_year_eol
    assert first["actual_vat_yuan"] <= first["output_vat_yuan"]
    assert result["full_pre_tax_irr"] is not None


def test_input_vat_credit_carries_forward_and_pre_tax_cashflow_is_exposed():
    result = calculate_financials(FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=20_000_000,
        vat_rate=0.13, input_vat_rate_equipment=0.13,
        equipment_investment_share=1, input_vat_credit_ratio=1,
    ).financial())
    first = result["yearly"][0]
    assert first["input_vat_credit_used_yuan"] == pytest.approx(first["output_vat_yuan"])
    assert first["actual_vat_yuan"] == pytest.approx(0)
    assert first["input_vat_credit_closing_yuan"] > 0
    assert any(item["actual_vat_yuan"] > 0 for item in result["yearly"])
    assert len(result["pre_tax_cashflows_yuan"]) == len(result["cashflows_yuan"])


def test_revenue_phase_rules_apply_window_growth_and_eol_policy():
    parameters = FinancialTaskParameters(
        power_mw=10, capacity_mwh=20, annual_revenue_yuan=0,
        capacity_fee_yuan=1_000_000,
        revenue_phases={"capacity_fee_yuan": {
            "start_year": 2, "end_year": 4, "eol_applies": False, "annual_growth": 0.1,
        }},
        operation_years=5,
    )
    result = calculate_financials(parameters.financial())
    values = [item["capacity_fee_yuan"] for item in result["yearly"]]
    assert values == pytest.approx([0, 1_000_000, 1_100_000, 1_210_000, 0])


def test_calendar_cycle_eol_uses_annual_cycles_against_cycle_life():
    parameters = FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=8_000_000,
        eol_method="calendar_cycle_min", annual_cycles=350, cycle_life_cycles=8_000,
    )
    result = calculate_financials(parameters.financial())
    assert result["yearly"][0]["eol"] == pytest.approx(0.95625)


def test_desktop_template_eol_reproduces_hand_authored_curve_and_restart():
    parameters = FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=8_000_000,
        eol_method="desktop_template", replace_year=3,
        calendar_eol_table=[1.0, 0.995, 0.99, 0.985, 0.98],
    )
    result = calculate_financials(parameters.financial())
    # Desktop 1.6.6 uses 0.99 for the first curve year and restarts the curve
    # when a battery is replaced in year three.
    assert [item["eol"] for item in result["yearly"][:4]] == pytest.approx(
        [0.99, 0.9725, 0.99, 0.9725]
    )


def test_auxiliary_cycles_are_traceable_and_reduce_cycle_eol():
    parameters = FinancialTaskParameters(
        power_mw=100, capacity_mwh=200, annual_revenue_yuan=8_000_000,
        eol_method="calendar_cycle_min", annual_cycles=350,
        auxiliary_annual_cycles=150, cycle_life_cycles=8_000,
    )
    result = calculate_financials(parameters.financial())
    assert result["yearly"][0]["eol"] == pytest.approx(0.9375)
    assert parameters.model_dump()["auxiliary_annual_cycles"] == 150


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


def test_sensitivity_task_supports_template_operating_cost_driver():
    registry = RunRegistry()
    item = registry.submit("sensitivity", parameters={
        "base": {
            "power_mw": 100, "capacity_mwh": 200, "annual_revenue_yuan": 8_000_000,
            "fixed_operation_cost_yuan": 500_000,
        },
        "variable": "fixed_operation_cost_yuan", "change_rates": [-0.2, 0, 0.2],
    })
    assert run_once(registry)
    result = registry.get(item.run_id)
    assert result.status == "succeeded"
    assert result.result["points"][0]["full_npv_yuan"] > result.result["points"][-1]["full_npv_yuan"]
