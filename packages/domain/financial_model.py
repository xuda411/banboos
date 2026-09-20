"""Transparent project cash-flow model for the first server financial release."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise
from math import isfinite

MODEL_VERSION = "banboos-financial-1.1.0"


class FinancialError(ValueError):
    pass


@dataclass(frozen=True)
class FinancialParameters:
    power_mw: float
    capacity_mwh: float
    annual_revenue_yuan: float
    single_side_efficiency: float = 0.92
    dod: float = 0.95
    annual_cycles: float = 350.0
    eol_method: str = "linear"
    calendar_eol_decline: float = 0.015
    cycle_life_cycles: float = 8000.0
    capacity_lease_yuan: float = 0.0
    capacity_fee_yuan: float = 0.0
    subsidy_yuan: float = 0.0
    primary_frequency_yuan: float = 0.0
    secondary_frequency_yuan: float = 0.0
    capex_yuan_per_wh: float = 1.2
    operation_years: int = 25
    om_rate: float = 0.0075
    om_growth: float = 0.01
    land_rent_yuan: float = 0.0
    insurance_rate: float = 0.0
    fixed_operation_cost_yuan: float = 0.0
    revenue_share_threshold_yuan: float = 0.0
    revenue_share_rate: float = 0.0
    other_operating_cost_yuan: float = 0.0
    first_year_eol: float = 0.97
    final_eol: float = 0.80
    residual_rate: float = 0.02
    income_tax_rate: float = 0.25
    vat_rate: float = 0.0
    vat_surcharge_rate: float = 0.12
    stamp_tax_rate: float = 0.0
    discount_rate: float = 0.08
    loan_ratio: float = 0.0
    loan_years: int = 10
    loan_rate: float = 0.045
    construction_years: float = 0.5
    construction_loan_rate: float = 0.045
    replace_year: int | None = None
    replace_capex_yuan: float = 0.0

    def validate(self) -> None:
        if any(v is not None and not isinstance(v, str)
               and (isinstance(v, bool) or not isfinite(float(v)))
               for v in asdict(self).values()):
            raise FinancialError("财务参数必须为有限数值")
        if self.power_mw <= 0 or self.capacity_mwh <= 0:
            raise FinancialError("功率和容量必须为正")
        if not 0 < self.single_side_efficiency <= 1 or not 0 < self.dod <= 1:
            raise FinancialError("单边效率和DOD必须在(0,1]之间")
        if self.annual_cycles < 0 or self.cycle_life_cycles <= 0:
            raise FinancialError("循环次数和循环寿命必须有效")
        if self.eol_method not in {"linear", "calendar_cycle_min"}:
            raise FinancialError("不支持的EOL计算方式")
        duration = self.capacity_mwh / self.power_mw
        if not 0.25 <= duration <= 24:
            raise FinancialError("容量/功率时长必须在0.25至24小时之间")
        if any(value < 0 for value in (self.annual_revenue_yuan, self.capacity_lease_yuan,
                                       self.capacity_fee_yuan, self.subsidy_yuan,
                                       self.primary_frequency_yuan, self.secondary_frequency_yuan,
                                       self.replace_capex_yuan, self.land_rent_yuan,
                                       self.fixed_operation_cost_yuan, self.revenue_share_threshold_yuan,
                                       self.other_operating_cost_yuan)):
            raise FinancialError("收入和换电池投资不能为负")
        if self.capex_yuan_per_wh <= 0:
            raise FinancialError("单位投资必须为正")
        if not 1 <= self.operation_years <= 100 or int(self.operation_years) != self.operation_years:
            raise FinancialError("运营年限必须为1至100年的整数")
        if not 0 <= self.loan_ratio <= 1 or self.loan_years < 1 or self.loan_years > 100:
            raise FinancialError("贷款比例须在0至1之间，贷款期限须为正整数")
        if int(self.loan_years) != self.loan_years or self.loan_rate < 0:
            raise FinancialError("贷款期限和利率无效")
        if self.construction_years < 0 or self.construction_loan_rate < 0:
            raise FinancialError("建设期和建设期利率不能为负")
        if self.replace_year is not None and (self.replace_year < 1 or self.replace_year > self.operation_years):
            raise FinancialError("换电池年份必须在运营期内")
        for value in (self.om_rate, self.om_growth, self.residual_rate, self.income_tax_rate,
                      self.calendar_eol_decline, self.insurance_rate, self.revenue_share_rate,
                      self.vat_rate, self.vat_surcharge_rate, self.stamp_tax_rate):
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
    construction_interest = (p.initial_investment_yuan * p.loan_ratio * p.construction_loan_rate
                              * p.construction_years)
    total_investment = p.initial_investment_yuan + construction_interest
    depreciation = p.initial_investment_yuan * (1 - p.residual_rate) / years
    loan_principal = p.initial_investment_yuan * p.loan_ratio
    annual_principal = loan_principal / p.loan_years if loan_principal else 0.0
    replacement_depreciation = (p.replace_capex_yuan * (1 - p.residual_rate)
                                / max(1, years - (p.replace_year or years) + 1)
                                if p.replace_capex_yuan and p.replace_year else 0.0)
    yearly: list[dict] = []
    cashflows = [-total_investment]
    equity_cashflows = [-(total_investment - loan_principal)]
    remaining_loan = loan_principal
    for year in range(1, years + 1):
        age = year
        if p.replace_year and year >= p.replace_year:
            age = year - p.replace_year + 1
        linear_eol = p.first_year_eol + (p.final_eol - p.first_year_eol) * (age - 1) / max(1, years - 1)
        calendar_eol = max(p.final_eol, 1 - p.calendar_eol_decline * age)
        # Cycle life is the total usable cycle count, so the annual loss is
        # cumulative cycles divided by that lifetime, bounded by final EOL.
        cycle_eol = max(p.final_eol, 1 - p.annual_cycles * age / p.cycle_life_cycles)
        eol = min(linear_eol, calendar_eol, cycle_eol) if p.eol_method == "calendar_cycle_min" else linear_eol
        energy_revenue = p.annual_revenue_yuan * eol
        capacity_fee = p.capacity_fee_yuan * eol
        subsidy = p.subsidy_yuan * eol
        revenue = (energy_revenue + capacity_fee + subsidy + p.capacity_lease_yuan
                   + p.primary_frequency_yuan + p.secondary_frequency_yuan)
        output_vat = revenue / (1 + p.vat_rate) * p.vat_rate if p.vat_rate else 0.0
        net_revenue = revenue - output_vat
        vat_surcharge = output_vat * p.vat_surcharge_rate
        stamp_tax = net_revenue * p.stamp_tax_rate
        revenue_share = max(0.0, net_revenue - p.revenue_share_threshold_yuan) * p.revenue_share_rate
        replacement = p.replace_capex_yuan if p.replace_year == year else 0.0
        insurance = p.initial_investment_yuan * p.insurance_rate
        operating_cost = (total_investment * p.om_rate * (1 + p.om_growth) ** (year - 1)
                          + p.land_rent_yuan + insurance + p.fixed_operation_cost_yuan
                          + p.other_operating_cost_yuan + revenue_share)
        depreciation_this_year = depreciation + (replacement_depreciation if p.replace_year and year >= p.replace_year else 0.0)
        taxable_profit = net_revenue - operating_cost - depreciation_this_year - vat_surcharge - stamp_tax
        income_tax = max(0.0, taxable_profit * p.income_tax_rate)
        net_profit = taxable_profit - income_tax
        interest = remaining_loan * p.loan_rate if year <= p.loan_years else 0.0
        principal = annual_principal if year <= p.loan_years else 0.0
        if year == years:
            principal += remaining_loan - principal
        remaining_loan = max(0.0, remaining_loan - principal)
        project_cashflow = net_profit + depreciation_this_year - replacement - output_vat - vat_surcharge - stamp_tax
        equity_taxable_profit = taxable_profit - interest
        equity_tax = max(0.0, equity_taxable_profit * p.income_tax_rate)
        # This starts from cash revenue, not net profit: depreciation is already excluded.
        equity_cashflow = net_revenue - operating_cost - replacement - interest - principal - equity_tax - output_vat - vat_surcharge - stamp_tax
        cashflows.append(project_cashflow)
        equity_cashflows.append(equity_cashflow)
        yearly.append({"year": year, "eol": eol, "revenue_yuan": revenue,
                       "gross_revenue_yuan": revenue, "net_revenue_yuan": net_revenue,
                       "output_vat_yuan": output_vat, "vat_surcharge_yuan": vat_surcharge,
                       "stamp_tax_yuan": stamp_tax, "revenue_share_yuan": revenue_share,
                       "insurance_yuan": insurance,
                       "energy_revenue_yuan": energy_revenue,
                       "capacity_fee_yuan": capacity_fee, "subsidy_yuan": subsidy,
                       "capacity_lease_yuan": p.capacity_lease_yuan,
                       "primary_frequency_yuan": p.primary_frequency_yuan,
                       "secondary_frequency_yuan": p.secondary_frequency_yuan,
                       "operating_cost_yuan": operating_cost, "depreciation_yuan": depreciation_this_year,
                       "replacement_capex_yuan": replacement, "loan_interest_yuan": interest,
                       "loan_principal_yuan": principal, "remaining_loan_yuan": remaining_loan,
                       "equity_tax_yuan": equity_tax,
                       "taxable_profit_yuan": taxable_profit, "income_tax_yuan": income_tax,
                       "net_profit_yuan": net_profit, "project_cashflow_yuan": project_cashflow,
                       "equity_cashflow_yuan": equity_cashflow})
    cumulative = -total_investment
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
        "construction_interest_yuan": construction_interest,
        "total_investment_yuan": total_investment,
        "full_irr": irr(cashflows), "full_npv_yuan": npv(p.discount_rate, cashflows),
        "payback_year": payback, "equity_irr": irr(equity_cashflows),
        "equity_npv_yuan": npv(p.discount_rate, equity_cashflows),
        "yearly": yearly, "equity_cashflows_yuan": equity_cashflows,
        "model_version": MODEL_VERSION,
        "cashflows_yuan": cashflows,
    }
