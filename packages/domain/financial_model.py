"""Transparent project cash-flow model for the first server financial release."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise
from math import isfinite


class FinancialError(ValueError):
    pass


@dataclass(frozen=True)
class FinancialParameters:
    power_mw: float
    capacity_mwh: float
    annual_revenue_yuan: float
    capex_yuan_per_wh: float = 1.2
    operation_years: int = 25
    om_rate: float = 0.0075
    om_growth: float = 0.01
    first_year_eol: float = 0.97
    final_eol: float = 0.80
    residual_rate: float = 0.02
    income_tax_rate: float = 0.25
    discount_rate: float = 0.08

    def validate(self) -> None:
        if any(isinstance(v, bool) or not isfinite(float(v)) for v in asdict(self).values()):
            raise FinancialError("财务参数必须为有限数值")
        if self.power_mw <= 0 or self.capacity_mwh <= 0 or self.annual_revenue_yuan < 0:
            raise FinancialError("功率、容量必须为正，年收入不能为负")
        if self.capex_yuan_per_wh <= 0:
            raise FinancialError("单位投资必须为正")
        if not 1 <= self.operation_years <= 100 or int(self.operation_years) != self.operation_years:
            raise FinancialError("运营年限必须为1至100年的整数")
        for value in (self.om_rate, self.om_growth, self.residual_rate, self.income_tax_rate):
            if value < 0 or value > 1:
                raise FinancialError("费率和残值率必须在0至1之间")
        if not 0 < self.first_year_eol <= 1 or not 0 < self.final_eol <= 1:
            raise FinancialError("EOL必须在(0,1]之间")
        if self.discount_rate <= -1:
            raise FinancialError("折现率必须大于-100%")

    @property
    def initial_investment_yuan(self) -> float:
        return self.capacity_mwh * 1_000_000 * self.capex_yuan_per_wh


def npv(rate: float, cashflows: list[float]) -> float:
    if rate <= -1 or not all(isfinite(float(value)) for value in cashflows):
        raise FinancialError("现金流或折现率无效")
    return sum(value / (1 + rate) ** year for year, value in enumerate(cashflows))


def irr(cashflows: list[float]) -> float | None:
    if not cashflows or not all(isfinite(float(value)) for value in cashflows):
        return None
    if not any(value < 0 for value in cashflows) or not any(value > 0 for value in cashflows):
        return None
    # Scan a bounded, logarithmic rate grid and only return a unique root.
    grid = [-0.9999, -0.99, -0.9, -0.75, -0.5, -0.25, 0, 0.05, 0.1, 0.2, 0.4,
            0.8, 1.5, 3, 7, 15, 31]
    roots: list[float] = []
    for left, right in pairwise(grid):
        f_left, f_right = npv(left, cashflows), npv(right, cashflows)
        if f_left == 0:
            roots.append(left)
            continue
        if f_left * f_right > 0:
            continue
        for _ in range(100):
            middle = (left + right) / 2
            f_middle = npv(middle, cashflows)
            if abs(f_middle) < 1e-7:
                break
            if f_left * f_middle <= 0:
                right, f_right = middle, f_middle
            else:
                left, f_left = middle, f_middle
        roots.append((left + right) / 2)
    unique = []
    for root in roots:
        if not unique or abs(root - unique[-1]) > 1e-6:
            unique.append(root)
    return unique[0] if len(unique) == 1 else None


def calculate_financials(p: FinancialParameters) -> dict:
    p.validate()
    years = int(p.operation_years)
    depreciation = p.initial_investment_yuan * (1 - p.residual_rate) / years
    yearly: list[dict] = []
    cashflows = [-p.initial_investment_yuan]
    for year in range(1, years + 1):
        eol = p.first_year_eol + (p.final_eol - p.first_year_eol) * (year - 1) / max(1, years - 1)
        revenue = p.annual_revenue_yuan * eol
        operating_cost = p.initial_investment_yuan * p.om_rate * (1 + p.om_growth) ** (year - 1)
        taxable_profit = revenue - operating_cost - depreciation
        income_tax = max(0.0, taxable_profit * p.income_tax_rate)
        net_profit = taxable_profit - income_tax
        project_cashflow = net_profit + depreciation
        cashflows.append(project_cashflow)
        yearly.append({"year": year, "eol": eol, "revenue_yuan": revenue,
                       "operating_cost_yuan": operating_cost, "depreciation_yuan": depreciation,
                       "taxable_profit_yuan": taxable_profit, "income_tax_yuan": income_tax,
                       "net_profit_yuan": net_profit, "project_cashflow_yuan": project_cashflow})
    cumulative = -p.initial_investment_yuan
    payback = None
    for year, value in enumerate(cashflows[1:], start=1):
        before = cumulative
        cumulative += value
        if before < 0 <= cumulative and value > 0:
            payback = year - 1 + (-before / value)
            break
    return {
        "power_mw": p.power_mw, "capacity_mwh": p.capacity_mwh,
        "duration_hours": p.capacity_mwh / p.power_mw,
        "initial_investment_yuan": p.initial_investment_yuan,
        "full_irr": irr(cashflows), "full_npv_yuan": npv(p.discount_rate, cashflows),
        "payback_year": payback, "yearly": yearly,
        "model_version": "banboos-financial-1.0.0",
        "cashflows_yuan": cashflows,
    }
