from itertools import combinations

import pytest
from pydantic import ValidationError

from packages.contracts.portfolio import PortfolioTaskParameters
from packages.domain.portfolio_optimizer import ALGORITHM_VERSION, optimize_portfolio


def project(name, cost, revenue):
    return dict(name=name, capacity_mwh=cost / 100, unit_investment_yuan_wh=1,
                annual_revenue_wan=revenue)


@pytest.mark.parametrize('objective', ['max_npv', 'max_irr', 'min_investment'])
def test_selection_matches_independent_exhaustive_reference(objective):
    projects = [project('甲', 700, 160), project('乙', 500, 140),
                project('丙', 500, 135), project('丁', 800, 0)]
    parameters = PortfolioTaskParameters(objective=objective, projects=projects,
                                        budget_limit_wan=1000, revenue_target_wan=260)
    actual = optimize_portfolio(parameters)
    subsets = [group for size in range(1, 5) for group in combinations(projects, size)]
    cost = lambda group: sum(p['capacity_mwh'] * 100 for p in group)
    revenue = lambda group: sum(p['annual_revenue_wan'] for p in group)
    candidates = [group for group in subsets if cost(group) <= 1000]
    factor = sum(1 / 1.08 ** year for year in range(1, 16))
    if objective == 'min_investment':
        expected = min((g for g in candidates if revenue(g) >= 260), key=cost)
    else:
        metric = (lambda g: revenue(g) * factor - cost(g)) if objective == 'max_npv' else (lambda g: revenue(g) / cost(g))
        expected = max(candidates, key=metric)
    assert {p['name'] for p in actual['selected_projects']} == {p['name'] for p in expected}
    assert actual['total_investment_wan'] == cost(expected)
    assert actual['total_npv_wan'] == pytest.approx(revenue(expected) * factor - cost(expected))
    assert actual['total_annual_revenue_wan'] == revenue(expected)
    assert sum(p['annual_revenue_wan'] for p in actual['selected_projects']) == revenue(expected)
    assert actual['algorithm_version'] == ALGORITHM_VERSION
    assert actual['outcome'] == 'optimal'


def test_all_50_candidates_are_considered():
    projects = [project(str(i), 100, 0) for i in range(49)] + [project('第50个', 100, 40)]
    result = optimize_portfolio(PortfolioTaskParameters(
        objective='max_npv', budget_limit_wan=100, projects=projects))
    assert [p['name'] for p in result['selected_projects']] == ['第50个']


@pytest.mark.parametrize('objective', ['max_npv', 'max_irr'])
def test_empty_selection_is_explicit_and_irr_is_not_zero(objective):
    result = optimize_portfolio(PortfolioTaskParameters(
        objective=objective, budget_limit_wan=200, projects=[project('甲', 100, 0)]))
    assert result['selected_projects'] == []
    assert result['outcome'] == 'no_selection'
    assert result['portfolio_irr'] is None


def test_infeasible_target_is_not_reported_as_optimal():
    result = optimize_portfolio(PortfolioTaskParameters(
        objective='min_investment', budget_limit_wan=50, revenue_target_wan=30,
        projects=[project('甲', 100, 40)]))
    assert result['outcome'] == 'infeasible'
    assert result['selected_projects'] == []


def test_zero_discount_rate_has_exact_annuity_value():
    result = optimize_portfolio(PortfolioTaskParameters(
        objective='max_npv', budget_limit_wan=100, discount_rate=0, operation_years=10,
        projects=[project('甲', 100, 40)]))
    assert result['total_npv_wan'] == 300


@pytest.mark.parametrize('payload', [
    dict(objective='max_npv', projects=[]),
    dict(objective='max_npv', projects=[project('甲', 100, 40)]),
    dict(objective='min_investment', projects=[project('甲', 100, 40)]),
    dict(objective='max_irr', budget_limit_wan=100, projects=[project(' ', 100, 40)]),
    dict(objective='max_npv', budget_limit_wan=100, projects=[project(str(i), 100, 40) for i in range(51)]),
    dict(objective='max_npv', budget_limit_wan=100, projects=[project('甲', 100, float('nan'))]),
])
def test_invalid_assumptions_are_rejected(payload):
    with pytest.raises(ValidationError):
        PortfolioTaskParameters.model_validate(payload)
