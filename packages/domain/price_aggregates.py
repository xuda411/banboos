"""Reusable daily, monthly and annual price-window aggregates."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import isfinite


def aggregate_periods(records: list[dict], slots: int,
                      start_date: date | None = None, end_date: date | None = None) -> dict:
    """Aggregate complete 96-point curves with the finance window rule."""
    if type(slots) is not int or not 1 <= slots <= 96:
        raise ValueError("窗口点数必须为1至96的整数")
    grouped: dict[date, set[tuple[float, ...]]] = defaultdict(set)
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

    daily: list[dict] = []
    for day in sorted(grouped):
        source_stats = []
        source_means = []
        for curve in sorted(grouped[day]):
            windows = [sum(curve[i:i + slots]) / slots for i in range(97 - slots)]
            source_stats.append((min(windows), max(windows)))
            source_means.append(sum(curve) / len(curve))
        low = sum(item[0] for item in source_stats) / len(source_stats)
        high = sum(item[1] for item in source_stats) / len(source_stats)
        daily.append({
            "day": day,
            "average_price_yuan_per_mwh": sum(source_means) / len(source_means),
            "charge_price_yuan_per_mwh": low,
            "discharge_price_yuan_per_mwh": high,
            "spread_yuan_per_mwh": high - low,
            "min_price_yuan_per_mwh": min(item[0] for item in source_stats),
            "max_price_yuan_per_mwh": max(item[1] for item in source_stats),
            "source_count": len(source_stats),
        })

    def build(period_key: str) -> list[dict]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in daily:
            groups[row["day"].strftime(period_key)].append(row)
        result = []
        for period, rows in sorted(groups.items()):
            average = _mean(rows, "average_price_yuan_per_mwh")
            charge = _mean(rows, "charge_price_yuan_per_mwh")
            discharge = _mean(rows, "discharge_price_yuan_per_mwh")
            result.append({
                "period": period,
                "valid_days": len(rows),
                "average_price_yuan_per_mwh": average,
                "charge_price_yuan_per_mwh": charge,
                "discharge_price_yuan_per_mwh": discharge,
                "spread_yuan_per_mwh": discharge - charge,
                "min_price_yuan_per_mwh": min(row["min_price_yuan_per_mwh"] for row in rows),
                "max_price_yuan_per_mwh": max(row["max_price_yuan_per_mwh"] for row in rows),
                "multiple_source_days": sum(row["source_count"] > 1 for row in rows),
            })
        return result

    multiple_source_dates = [row["day"].isoformat() for row in daily if row["source_count"] > 1]
    missing_dates = []
    if start_date is not None and end_date is not None and end_date >= start_date:
        valid_dates = {row["day"] for row in daily}
        cursor = start_date
        while cursor <= end_date:
            if cursor not in valid_dates:
                missing_dates.append(cursor.isoformat())
            cursor += timedelta(days=1)
    return {
        "monthly": build("%Y-%m"),
        "annual": build("%Y"),
        "valid_days": len(daily),
        "available_days": len(grouped),
        "excluded_records": excluded,
        "multiple_source_days": sum(row["source_count"] > 1 for row in daily),
        "multiple_source_dates": multiple_source_dates,
        "missing_dates": missing_dates,
        "first_date": daily[0]["day"].isoformat() if daily else None,
        "last_date": daily[-1]["day"].isoformat() if daily else None,
    }


def _mean(rows: list[dict], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows)
