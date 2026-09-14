"""1.6.6 continuous-window financial baseline; pure, replayable daily weighting."""
from collections import defaultdict
from datetime import date, timedelta
from math import isfinite

ALGORITHM_VERSION = "annual_valid_day_window_mean_v1"


def annual_window_average(records: list[dict], slots: int) -> dict:
    if type(slots) is not int or not 1 <= slots <= 96:
        raise ValueError("窗口点数必须为1至96的整数")
    grouped = defaultdict(set)
    excluded = 0
    for record in records:
        try:
            day = date.fromisoformat(str(record["run_date"])[:10])
            values = tuple(float(value) for value in record["prices"])
            if len(values) != 96 or not all(isfinite(value) for value in values):
                raise ValueError("不是完整的96点有效曲线")
        except (KeyError, ValueError, TypeError, OverflowError):
            excluded += 1
            continue
        grouped[day].add(values)
    days = sorted(grouped)
    if not days:
        raise ValueError("该节点没有完整的96点有效日")
    complete = None
    run_start, previous = days[0], None
    for day in days:
        if previous is not None and day != previous + timedelta(days=1):
            run_start = day
        exclusive = day + timedelta(days=1)
        try:
            year_start = exclusive.replace(year=exclusive.year - 1)
        except ValueError:
            year_start = exclusive.replace(year=exclusive.year - 1, day=28)
        if run_start <= year_start:
            complete = (year_start, day)
        previous = day
    start, end = complete or (days[0], days[-1])
    selected = [day for day in days if start <= day <= end]
    daily = []
    for day in selected:
        source_stats = []
        for curve in sorted(grouped[day]):
            means = [sum(curve[i:i + slots]) / slots for i in range(97 - slots)]
            source_stats.append((min(means), max(means)))
        daily.append(tuple(sum(values[index] for values in source_stats) / len(source_stats)
                           for index in (0, 1)))
    low, high = (sum(values[index] for values in daily) / len(daily) for index in (0, 1))
    return {"charge_price_yuan_per_mwh": low, "discharge_price_yuan_per_mwh": high,
            "spread_yuan_per_mwh": high - low, "valid_days": len(selected),
            "available_days": len(days), "start_date": start.isoformat(),
            "end_date": end.isoformat(), "excluded_records": excluded,
            "multiple_source_days": sum(len(grouped[day]) > 1 for day in selected),
            "baseline_policy": "latest_complete_year" if complete else "all_valid_days"}
