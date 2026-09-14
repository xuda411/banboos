"""96-period historical dispatch; port of the 1.6.6 strict MILP rules.

Units: MW, MWh, yuan/MWh; SOC is the end of each 15-minute interval.
No UI, database or network dependencies. This is hindsight, not a forecast.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise
from math import isfinite

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

ALGORITHM_VERSION = "banboos-strict-dispatch-1.0.0"
PERIODS = 96
DT = 0.25
SEGMENTS = 24
MIP_GAP = 1e-5


class DispatchError(ValueError):
    def __init__(self, message: str, code: str = "INVALID_DISPATCH_INPUT"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BatteryParameters:
    power_mw: float
    capacity_mwh: float
    eta_charge: float = 0.92
    eta_discharge: float = 0.92
    soc_min: float = 0.05
    soc_max: float = 0.95
    soc_initial: float = 0.50
    max_daily_cycles: float = 2.0
    hurdle_yuan_per_mwh: float = 50.0
    degradation_alpha: float = 0.0
    min_daily_revenue_yuan: float = 0.0
    line_loss_yuan_per_mwh: float = 20.7
    transmission_yuan_per_mwh: float = 150.3
    system_operation_yuan_per_mwh: float = 56.5
    cross_subsidy_yuan_per_mwh: float = 7.3

    def validate(self) -> None:
        if any(isinstance(v, bool) or not isfinite(float(v)) for v in asdict(self).values()):
            raise DispatchError("所有电池参数必须为有限数值")
        if self.power_mw <= 0 or self.capacity_mwh <= 0:
            raise DispatchError("功率和容量必须大于零")
        if not (0 < self.eta_charge <= 1 and 0 < self.eta_discharge <= 1):
            raise DispatchError("充电、放电单程效率须在 (0,1] 内")
        if not (0 <= self.soc_min <= self.soc_initial <= self.soc_max <= 1
                and self.soc_min < self.soc_max):
            raise DispatchError("SOC须满足0≤下限≤初值≤上限≤1，且下限小于上限")
        if min(self.max_daily_cycles, self.hurdle_yuan_per_mwh, self.degradation_alpha,
               self.min_daily_revenue_yuan) < 0:
            raise DispatchError("循环次数、门槛和衰减成本不能为负")

    @property
    def duration_hours(self) -> float:
        return self.capacity_mwh / self.power_mw


@dataclass(frozen=True)
class DispatchResult:
    charge_mw: list[float]
    discharge_mw: list[float]
    soc: list[float]
    charge_energy_mwh: float
    discharge_energy_mwh: float
    charge_cost_yuan: float
    discharge_revenue_yuan: float
    hurdle_cost_yuan: float
    degradation_cost_yuan: float
    net_revenue_yuan: float
    cycles: float
    shutdown: bool
    solver_gap: float
    degradation_approximation_bound_yuan: float


def validate_trajectory(charge, discharge, soc, p: BatteryParameters) -> None:
    """Independently audit physical constraints after the solver returns."""
    ch, dis, state = (np.asarray(x, dtype=float) for x in (charge, discharge, soc))
    if not all(x.shape == (PERIODS,) and np.all(np.isfinite(x)) for x in (ch, dis, state)):
        raise DispatchError("求解结果含无效数值", "INVALID_TRAJECTORY")
    before = np.r_[p.soc_initial, state[:-1]]
    expected = before + ch * p.eta_charge * DT / p.capacity_mwh
    expected -= dis * DT / (p.eta_discharge * p.capacity_mwh)
    invalid = (
        np.max(np.abs(state - expected)) > 1e-6
        or abs(state[-1] - p.soc_initial) > 1e-6
        or min(ch.min(), dis.min()) < -1e-5
        or max(ch.max(), dis.max()) > p.power_mw + 1e-5
        or state.min() < p.soc_min - 1e-6 or state.max() > p.soc_max + 1e-6
        or np.any((ch > 1e-5) & (dis > 1e-5))
        or (ch + dis).sum() * DT / (2 * p.capacity_mwh) > p.max_daily_cycles + 1e-6
    )
    if invalid:
        raise DispatchError("轨迹未通过能量守恒、互斥或设备边界检查", "INVALID_TRAJECTORY")


def solve_day(prices, p: BatteryParameters, time_limit_s: float = 30) -> DispatchResult:
    p.validate()
    try:
        spot = np.asarray(prices, dtype=float)
    except (TypeError, ValueError) as error:
        raise DispatchError("需要完整的96个有限电价") from error
    if spot.shape != (PERIODS,) or not np.all(np.isfinite(spot)):
        raise DispatchError("需要完整的96个有限电价，不插补缺失点")
    if not isfinite(time_limit_s) or not 0 < time_limit_s <= 30:
        raise DispatchError("单日求解时间上限须在 (0,30] 秒内")
    n = PERIODS
    quadratic = p.degradation_alpha > 0
    size = n * (6 if quadratic else 4)
    rows = n + 1 + 2 * n + 1 + (2 * n * SEGMENTS if quadratic else 0)
    matrix = lil_matrix((rows, size))
    lower, upper = np.full(rows, -np.inf), np.full(rows, np.inf)
    charge_price = spot + p.line_loss_yuan_per_mwh + p.transmission_yuan_per_mwh
    charge_price += p.system_operation_yuan_per_mwh
    discharge_price = spot + p.transmission_yuan_per_mwh + p.cross_subsidy_yuan_per_mwh
    objective = np.zeros(size)
    objective[:n] = charge_price * DT
    objective[n:2*n] = (p.hurdle_yuan_per_mwh - discharge_price) * DT
    lo, hi = np.zeros(size), np.full(size, np.inf)
    hi[:2*n] = p.power_mw
    lo[2*n:3*n], hi[2*n:3*n] = p.soc_min, p.soc_max
    hi[3*n:4*n] = 1
    integer = np.zeros(size)
    integer[3*n:4*n] = 1
    row = 0
    for t in range(n):
        matrix[row, 2*n+t] = 1
        matrix[row, t] = -p.eta_charge * DT / p.capacity_mwh
        matrix[row, n+t] = DT / (p.eta_discharge * p.capacity_mwh)
        if t:
            matrix[row, 2*n+t-1] = -1
        lower[row] = upper[row] = p.soc_initial if t == 0 else 0
        row += 1
    matrix[row, 3*n-1] = 1
    lower[row] = upper[row] = p.soc_initial
    row += 1
    for t in range(n):
        matrix[row, t], matrix[row, 3*n+t] = 1, -p.power_mw
        upper[row] = 0
        row += 1
        matrix[row, n+t], matrix[row, 3*n+t] = 1, p.power_mw
        upper[row] = p.power_mw
        row += 1
    matrix[row, :2*n] = DT / (2 * p.capacity_mwh)
    upper[row] = p.max_daily_cycles
    row += 1
    if quadratic:
        objective[4*n:] = p.degradation_alpha * DT
        knots = np.linspace(0, p.power_mw, SEGMENTS+1)
        for j in range(2*n):
            for left, right in pairwise(knots):
                matrix[row, j], matrix[row, 4*n+j] = left+right, -1
                upper[row] = left*right
                row += 1
    result = milp(objective, integrality=integer, bounds=Bounds(lo, hi),
                  constraints=LinearConstraint(matrix.tocsr(), lower, upper),
                  options={"time_limit": time_limit_s, "mip_rel_gap": MIP_GAP})
    if not result.success or result.status != 0 or result.x is None:
        code = "SOLVER_LIMIT" if result.status == 1 else "SOLVER_FAILED"
        raise DispatchError(f"MILP未收敛，不发布候选收益：{result.message}", code)
    ch, dis, soc = (result.x[i*n:(i+1)*n] for i in range(3))
    validate_trajectory(ch, dis, soc, p)
    charge_cost, revenue = float(ch @ charge_price * DT), float(dis @ discharge_price * DT)
    energy_ch, energy_dis = float(ch.sum() * DT), float(dis.sum() * DT)
    hurdle = energy_dis * p.hurdle_yuan_per_mwh
    degradation = float((ch @ ch + dis @ dis) * p.degradation_alpha * DT)
    net = revenue - charge_cost - hurdle - degradation
    shutdown = net < max(0, p.min_daily_revenue_yuan) - 1e-6
    if shutdown:
        ch, dis, soc = np.zeros(n), np.zeros(n), np.full(n, p.soc_initial)
        energy_ch = energy_dis = charge_cost = revenue = hurdle = degradation = net = 0.0
    bound = n * p.degradation_alpha * DT * (p.power_mw / SEGMENTS)**2 / 4
    return DispatchResult(
        ch.tolist(), dis.tolist(), soc.tolist(), energy_ch, energy_dis,
        charge_cost, revenue, hurdle, degradation, net,
        (energy_ch + energy_dis) / (2 * p.capacity_mwh), shutdown,
        float(result.mip_gap or 0), bound,
    )
