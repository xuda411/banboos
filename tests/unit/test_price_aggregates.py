from datetime import date

from packages.domain.price_aggregates import aggregate_periods


def curve(day, high=100):
    return {"run_date": day, "prices": [0] * 48 + [high] * 48}


def test_aggregates_month_and_year_weight_valid_days_once():
    rows = [curve("2026-01-01", 100), curve("2026-01-01", 300), curve("2026-02-01", 500),
            {"run_date": "2026-02-02", "prices": [None] * 96}]
    result = aggregate_periods(rows, 8)
    assert result["valid_days"] == 2
    assert result["excluded_records"] == 1
    assert result["multiple_source_days"] == 1
    assert result["multiple_source_dates"] == ["2026-01-01"]
    assert result["missing_dates"] == []
    assert [(row["period"], row["valid_days"]) for row in result["monthly"]] == [
        ("2026-01", 1), ("2026-02", 1)
    ]
    assert result["annual"][0]["valid_days"] == 2
    assert result["annual"][0]["discharge_price_yuan_per_mwh"] == 350


def test_aggregates_report_missing_dates_in_requested_range():
    result = aggregate_periods([curve("2026-01-01")], 8, date(2026, 1, 1), date(2026, 1, 3))
    assert result["missing_dates"] == ["2026-01-02", "2026-01-03"]


def test_aggregates_reject_non_integer_quarter_hour_window():
    import pytest

    with pytest.raises(ValueError):
        aggregate_periods([curve("2026-01-01")], 7.5)
