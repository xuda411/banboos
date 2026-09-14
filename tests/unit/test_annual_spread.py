from datetime import date, timedelta

import pytest

from packages.domain.annual_spread import annual_window_average


def curve(day, high=100):
    return {"run_date": str(day), "prices": [0] * 48 + [high] * 48}


def test_continuous_windows_do_not_select_disjoint_extreme_points():
    result = annual_window_average([{"run_date": "2026-01-01", "prices": [0, 100] * 48}], 8)
    assert result["spread_yuan_per_mwh"] == 0
    assert result["charge_price_yuan_per_mwh"] == 50


def test_sources_are_deduplicated_then_days_are_equally_weighted():
    rows = [curve("2026-01-01", 100)] * 5 + [curve("2026-01-01", 300), curve("2026-01-02", 500)]
    rows.append({"run_date": "2026-01-03", "prices": [None] * 96})
    result = annual_window_average(rows, 16)
    assert result["discharge_price_yuan_per_mwh"] == 350
    assert result["valid_days"] == 2
    assert result["multiple_source_days"] == 1
    assert result["excluded_records"] == 1
    assert result["baseline_policy"] == "all_valid_days"


def test_latest_complete_twelve_months_preserves_leap_year():
    first = date(2024, 1, 1)
    rows = [curve(first + timedelta(days=index)) for index in range(366)]
    rows.append(curve("2025-02-01", 10000))
    result = annual_window_average(rows, 8)
    assert result["baseline_policy"] == "latest_complete_year"
    assert (result["start_date"], result["end_date"]) == ("2024-01-01", "2024-12-31")
    assert result["valid_days"] == 366
    assert result["available_days"] == 367
    assert result["discharge_price_yuan_per_mwh"] == 100


def test_calendar_span_does_not_imply_a_complete_year():
    result = annual_window_average([curve("2024-01-01"), curve("2026-01-01", 300)], 16)
    assert result["baseline_policy"] == "all_valid_days"
    assert result["valid_days"] == 2
    assert result["discharge_price_yuan_per_mwh"] == 200
    with pytest.raises(ValueError, match="没有完整"):
        annual_window_average([], 16)
