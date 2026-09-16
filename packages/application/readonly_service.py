"""Read-only application service used by both HTTP and future desktop adapters."""
from __future__ import annotations

import os
from datetime import date, datetime
from math import isfinite

from packages.contracts.analysis import PriceAnalysisResult
from packages.contracts.readonly import (
    DataQualitySummary,
    NodeSummary,
    PriceCurve,
    PriceRange,
    PriceSummary,
    WeatherObservation,
    WeatherSummary,
)
from packages.domain.annual_spread import ALGORITHM_VERSION as BASELINE_VERSION
from packages.domain.annual_spread import annual_window_average
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots
from packages.infrastructure.legacy_sqlite import LegacySQLiteReader
from packages.infrastructure.staging_sqlite import StagingSQLiteReader


class ReadonlyService:
    def __init__(self, legacy_db: str | None = None, staging_db: str | None = None):
        configured = legacy_db or os.getenv("BANBOOS2_LEGACY_DB")
        staging = staging_db or (os.getenv("BANBOOS2_STAGING_DB") if legacy_db is None else None)
        self._legacy_reader = LegacySQLiteReader(configured) if configured else None
        self._reader = StagingSQLiteReader(staging) if staging else self._legacy_reader

    @property
    def data_mode(self) -> str:
        return "staging-readonly" if isinstance(self._reader, StagingSQLiteReader) else ("legacy-readonly" if self._reader else "demo")

    def nodes(self, province: str | None = None, query: str | None = None) -> list[NodeSummary]:
        if self._reader:
            return [NodeSummary.model_validate(row) for row in self._reader.list_nodes(province, query)]
        demo = [NodeSummary(id=1, name="演示储能节点", province="湖北"), NodeSummary(id=2, name="演示储能节点-广东", province="广东")]
        return [row for row in demo if (not province or row.province == province) and (not query or query in row.name)]

    def node_count(self) -> int:
        return self._reader.node_count() if self._reader else len(self.nodes())

    def legacy_management(self, kind: str, limit: int = 200) -> dict:
        if not self._legacy_reader:
            return {"items": [], "source_mode": self.data_mode, "table": kind}
        return {"items": self._legacy_reader.management_rows(kind, limit),
                "source_mode": "legacy-readonly", "table": kind}

    def price(self, node_id: int, market: str, start_date: date, end_date: date) -> PriceSummary:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if self._reader:
            return PriceSummary.model_validate(self._reader.price_summary(node_id, market, start_date, end_date))
        return PriceSummary(node_id=node_id, market=market, start_date=start_date, end_date=end_date,
                            valid_days=0, data_points=0, source_mode="demo")

    def price_range(self, node_id: int, market: str) -> PriceRange:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if self._reader:
            return PriceRange.model_validate(self._reader.price_range(node_id, market))
        return PriceRange(node_id=node_id, market=market, source_mode="demo")

    def curves(self, node_id: int, market: str, start_date: date, end_date: date,
               limit: int = 31) -> list[PriceCurve]:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if not 1 <= limit <= 31:
            raise ValueError("limit must be between 1 and 31")
        if not self._reader:
            return []
        rows = self._reader.price_curves(node_id, market, start_date, end_date)
        return [PriceCurve(node_id=node_id, market=market, run_date=row["run_date"],
                           prices=row["prices"], source_mode=self.data_mode)
                for row in rows[:limit]]

    def weather(self, node_id: int, start_time: datetime | None = None,
                end_time: datetime | None = None) -> WeatherSummary:
        if self._legacy_reader:
            return WeatherSummary.model_validate(self._legacy_reader.weather_summary(node_id, start_time, end_time))
        return WeatherSummary(node_id=node_id, observations=0, source_mode="unavailable")

    def weather_series(self, node_id: int, start_time: datetime | None = None,
                       end_time: datetime | None = None, limit: int = 744) -> list[WeatherObservation]:
        if end_time and start_time and end_time < start_time:
            raise ValueError("end_time must be on or after start_time")
        if not 1 <= limit <= 744:
            raise ValueError("limit must be between 1 and 744")
        if not self._legacy_reader:
            return []
        observations = self._legacy_reader.weather_observations(node_id, start_time, end_time, limit)
        result = []
        for row in observations:
            ghi = _finite_or_none(row["ghi_w_m2"])
            wind = _finite_or_none(row["wind_speed_m_s"])
            temp = _finite_or_none(row["temp_c"])
            ambient = temp if temp is not None else 25.0
            temp_factor = max(0.82, min(1.04, 1.0 - 0.004 * (ambient - 25.0)))
            pv = None if ghi is None else max(0.0, 100.0 * min(1.05, ghi / 1000.0)
                                              * 0.98 * temp_factor)
            wind_power = None if wind is None else _wind_power(wind, 100.0)
            result.append(WeatherObservation(node_id=node_id, data_time=row["data_time"],
                source=row["source"], ghi_w_m2=ghi, wind_speed_m_s=wind, temp_c=temp,
                pv_predict_power_mw=round(pv, 4) if pv is not None else None,
                wind_predict_power_mw=round(wind_power, 4) if wind_power is not None else None, source_mode="legacy-readonly"))
        return result

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
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if not all(isfinite(value) for value in (power_mw, capacity_mwh, round_trip_efficiency)):
            raise ValueError("功率、容量和效率必须是有限数值")
        if power_mw <= 0 or capacity_mwh <= 0:
            raise ValueError("power_mw and capacity_mwh must be positive")
        duration = capacity_mwh / power_mw
        if duration < 0.25 or duration > 24:
            raise ValueError("capacity_mwh / power_mw must be between 0.25 and 24 hours")
        if not 0 < round_trip_efficiency <= 1:
            raise ValueError("round_trip_efficiency must be in (0, 1]")
        slots = round(duration * 4)
        if abs(duration * 4 - slots) > 1e-6:
            raise ValueError("连续均价差时长须为15分钟的整数倍")
        if self._reader:
            curves = self._reader.baseline_curves(node_id, market)
            source_mode = self.data_mode
        else:
            curves = []
            source_mode = "demo"
        baseline = annual_window_average(curves, slots)
        # One equivalent daily cycle is an explicit investment assumption, not dispatch revenue.
        average = max(0.0, baseline["discharge_price_yuan_per_mwh"] * round_trip_efficiency
                      - baseline["charge_price_yuan_per_mwh"]) * capacity_mwh
        # Invalid points remain represented as null for a JSON-safe replay input.
        snapshot_curves = [{"run_date": row["run_date"],
                            "prices": [_finite_or_none(value) for value in row["prices"]]}
                           for row in curves]
        snapshot_id = DispatchSnapshots().put({
            "kind": "price-analysis", "algorithm_version": BASELINE_VERSION,
            "parameters": {"node_id": node_id, "market": market, "power_mw": power_mw,
                           "capacity_mwh": capacity_mwh, "round_trip_efficiency": round_trip_efficiency},
            "curves": snapshot_curves})
        return PriceAnalysisResult(
            node_id=node_id, market=market, **baseline,
            power_mw=power_mw, capacity_mwh=capacity_mwh, duration_hours=duration,
            average_daily_revenue_yuan=average, snapshot_id=snapshot_id,
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


def _finite_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _wind_power(speed: float, capacity: float) -> float:
    if speed < 3 or speed >= 25:
        return 0.0
    if speed >= 12:
        return capacity
    return capacity * ((speed**3 - 3**3) / (12**3 - 3**3))
