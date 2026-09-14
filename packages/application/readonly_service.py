"""Read-only application service used by both HTTP and future desktop adapters."""
from __future__ import annotations

import os
from datetime import date, datetime

from packages.contracts.analysis import PriceAnalysisResult
from packages.contracts.readonly import (
    DataQualitySummary,
    NodeSummary,
    PriceSummary,
    WeatherSummary,
)
from packages.infrastructure.legacy_sqlite import LegacySQLiteReader


class ReadonlyService:
    def __init__(self, legacy_db: str | None = None):
        configured = legacy_db or os.getenv("BANBOOS2_LEGACY_DB")
        self._reader = LegacySQLiteReader(configured) if configured else None

    @property
    def data_mode(self) -> str:
        return "legacy-readonly" if self._reader else "demo"

    def nodes(self, province: str | None = None, query: str | None = None) -> list[NodeSummary]:
        if self._reader:
            return [NodeSummary.model_validate(row) for row in self._reader.list_nodes(province, query)]
        demo = [NodeSummary(id=1, name="演示储能节点", province="湖北"), NodeSummary(id=2, name="演示储能节点-广东", province="广东")]
        return [row for row in demo if (not province or row.province == province) and (not query or query in row.name)]

    def price(self, node_id: int, market: str, start_date: date, end_date: date) -> PriceSummary:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if self._reader:
            return PriceSummary.model_validate(self._reader.price_summary(node_id, market, start_date, end_date))
        return PriceSummary(node_id=node_id, market=market, start_date=start_date, end_date=end_date,
                            valid_days=0, data_points=0, source_mode="demo")

    def weather(self, node_id: int, start_time: datetime | None = None,
                end_time: datetime | None = None) -> WeatherSummary:
        if self._reader:
            return WeatherSummary.model_validate(self._reader.weather_summary(node_id, start_time, end_time))
        return WeatherSummary(node_id=node_id, observations=0, source_mode="demo")

    def quality(self, node_id: int, market: str, start_date: date,
                end_date: date) -> DataQualitySummary:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if self._reader:
            return DataQualitySummary.model_validate(
                self._reader.quality_summary(node_id, market, start_date, end_date)
            )
        return DataQualitySummary(node_id=node_id, market=market, start_date=start_date,
                                  end_date=end_date, total_records=0, complete_records=0,
                                  incomplete_records=0, missing_cells=0, non_finite_cells=0,
                                  coverage_ratio=0.0, source_mode="demo")

    def analyze_price(self, node_id: int, market: str, start_date: date, end_date: date,
                      power_mw: float, capacity_mwh: float,
                      round_trip_efficiency: float = 0.92) -> PriceAnalysisResult:
        if power_mw <= 0 or capacity_mwh <= 0:
            raise ValueError("power_mw and capacity_mwh must be positive")
        duration = capacity_mwh / power_mw
        if duration < 0.25 or duration > 24:
            raise ValueError("capacity_mwh / power_mw must be between 0.25 and 24 hours")
        if not 0 < round_trip_efficiency <= 1:
            raise ValueError("round_trip_efficiency must be in (0, 1]")
        if self._reader:
            curves = self._reader.price_curves(node_id, market, start_date, end_date)
            source_mode = "legacy-readonly"
        else:
            curves = []
            source_mode = "demo"
        slots = max(1, min(96, round(duration * 4)))
        daily_values: list[float] = []
        slot_energy = power_mw * 0.25
        for curve in curves:
            prices = curve["prices"]
            low_indices = sorted(range(96), key=lambda index: prices[index])[:slots]
            remaining = [index for index in range(96) if index not in low_indices]
            high_indices = sorted(remaining, key=lambda index: prices[index], reverse=True)[:slots]
            spread = sum(prices[index] for index in high_indices) * round_trip_efficiency
            spread -= sum(prices[index] for index in low_indices)
            daily_values.append(max(0.0, spread * slot_energy))
        average = sum(daily_values) / len(daily_values) if daily_values else 0.0
        return PriceAnalysisResult(
            node_id=node_id, market=market, start_date=start_date, end_date=end_date,
            power_mw=power_mw, capacity_mwh=capacity_mwh, duration_hours=duration,
            valid_days=len(daily_values), average_daily_revenue_yuan=average,
            annualized_revenue_yuan=average * 365, source_mode=source_mode,
        )

    def dispatch_curves(self, node_id: int, market: str, start_date: date,
                        end_date: date) -> list[dict]:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if not self._reader:
            return []
        return self._reader.price_curves(node_id, market, start_date, end_date)
