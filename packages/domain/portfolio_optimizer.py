"""Whole-project selection with the desktop's constant annual cashflow convention."""
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from packages.domain.financial_model import irr

ALGORITHM_VERSION = "portfolio-milp-annuity-v1"
CASHFLOW_NOTE = "手工情景：第0期投入，每年净现金流恒定；未接入逐年财务现金流。"


def optimize_portfolio(parameters):
    projects = [p.model_dump() for p in parameters.projects]
    years, rate = parameters.operation_years, parameters.discount_rate
    factor = sum((1 + rate) ** -year for year in range(1, years + 1))
    for p in projects:
        p["investment_wan"] = p["capacity_mwh"] * p["unit_investment_yuan_wh"] * 100
        p["npv_wan"] = p["annual_revenue_wan"] * factor - p["investment_wan"]

    costs = np.array([p["investment_wan"] for p in projects])
    revenues = np.array([p["annual_revenue_wan"] for p in projects])
    budget = parameters.budget_limit_wan
    outcome, message = "optimal", "优化完成；结果基于手工净现金流假设。"
    if parameters.objective == "max_irr":
        # With equal life and level cashflows, aggregate revenue/cost is a weighted
        # average. The best feasible singleton therefore attains maximum IRR.
        eligible = [p for p in projects if p["investment_wan"] <= budget
                    and p["annual_revenue_wan"] > 0]
        selected = [max(eligible, key=lambda p: p["annual_revenue_wan"] / p["investment_wan"])] if eligible else []
    else:
        constraints = []
        if budget is not None:
            constraints.append(LinearConstraint(costs, -np.inf, budget))
        upper = np.ones(len(projects))
        if parameters.objective == "min_investment":
            objective = costs
            constraints.append(LinearConstraint(revenues, parameters.revenue_target_wan, np.inf))
        else:
            objective = -np.array([p["npv_wan"] for p in projects])
            upper[objective >= 0] = 0  # Desktop rule: skip nonpositive NPV projects.
        solution = milp(objective, integrality=np.ones(len(projects)),
                        bounds=Bounds(np.zeros(len(projects)), upper),
                        constraints=constraints, options={"time_limit": 10, "mip_rel_gap": 0})
        if solution.status == 2:
            outcome, message = "infeasible", "没有满足收益目标及预算约束的组合，请调整条件。"
            selected = []
        elif not solution.success:
            raise RuntimeError("组合求解未达到最优状态，请减少候选项目或调整约束后重试")
        else:
            selected = [p for p, value in zip(projects, solution.x, strict=True) if value > 0.5]
    if not selected and outcome == "optimal":
        outcome, message = "no_selection", "没有符合预算及目标的项目；最大 NPV 目标不选取非正 NPV 项目。"
    investment = sum(p["investment_wan"] for p in selected)
    revenue = sum(p["annual_revenue_wan"] for p in selected)
    return {
        "objective": parameters.objective, "selected_projects": selected,
        "total_investment_wan": investment,
        "total_npv_wan": sum(p["npv_wan"] for p in selected),
        "total_annual_revenue_wan": revenue,
        "portfolio_irr": irr([-investment] + [revenue] * years) if selected else None,
        "algorithm_version": ALGORITHM_VERSION, "outcome": outcome,
        "message": message, "cashflow_note": CASHFLOW_NOTE,
    }
