import numpy as np
import pytest

from packages.domain.storage_dispatch import BatteryParameters, DispatchError, solve_day


def test_strict_dispatch_respects_soc_and_exclusive_operation():
    prices = np.full(96, 50.0)
    prices[0], prices[40] = 10.0, 500.0
    result = solve_day(prices, BatteryParameters(power_mw=100, capacity_mwh=200))
    assert result.net_revenue_yuan > 0
    assert result.cycles <= 2.0 + 1e-6
    assert result.soc[-1] == pytest.approx(0.5, abs=1e-6)
    assert all(not (charge > 1e-5 and discharge > 1e-5)
               for charge, discharge in zip(result.charge_mw, result.discharge_mw, strict=True))


def test_strict_dispatch_rejects_incomplete_day_and_bad_parameters():
    with pytest.raises(DispatchError, match="96个"):
        solve_day([1.0] * 95, BatteryParameters(power_mw=100, capacity_mwh=200))
    with pytest.raises(DispatchError, match="功率和容量"):
        solve_day([1.0] * 96, BatteryParameters(power_mw=0, capacity_mwh=200))
