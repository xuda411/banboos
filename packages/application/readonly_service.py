"""Read-only application service used by both HTTP and future desktop adapters."""
from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from math import cos, isfinite, pi, sin

from packages.contracts.analysis import PriceAnalysisResult, PriceBaselineMonth, PriceWindowBaseline
from packages.contracts.operations_report import (
    OperationsReport,
    OperationsReportPeriod,
    OperationsReportProvince,
)
from packages.contracts.portfolio_candidates_result import PortfolioCandidatesResult
from packages.contracts.readonly import (
    DataQualitySummary,
    NodeSummary,
    PriceAggregateResult,
    PriceCurve,
    PriceRange,
    PriceSummary,
    WeatherObservation,
    WeatherSummary,
)
from packages.domain.annual_spread import ALGORITHM_VERSION as BASELINE_VERSION
from packages.domain.annual_spread import annual_window_average
from packages.domain.price_aggregates import aggregate_periods
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots
from packages.infrastructure.legacy_sqlite import LegacySQLiteReader
from packages.infrastructure.staging_sqlite import StagingSQLiteReader


class ReadonlyService:
    def __init__(self, legacy_db: str | None = None, staging_db: str | None = None):
        configured = legacy_db or os.getenv("BANBOOS2_LEGACY_DB")
        staging = staging_db or os.getenv("BANBOOS2_STAGING_DB")
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

    def operations_report(self, market: str, start_date: date, end_date: date,
                         duration_hours: float = 2.0) -> OperationsReport:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if duration_hours < 0.25 or duration_hours > 24:
            raise ValueError("duration_hours must be between 0.25 and 24")
        province_map: dict[str, dict] = {}
        period_map: dict[str, dict] = {}
        valid_nodes = total_days = total_points = 0
        nodes = self.nodes()
        for node in nodes:
            aggregate = self.price_aggregates(node.id, market, start_date, end_date, duration_hours)
            province = node.province or "未配置省份"
            entry = province_map.setdefault(province, {"node_count": 0, "valid_nodes": 0,
                                                       "valid_days": 0, "data_points": 0})
            entry["node_count"] += 1
            entry["valid_days"] += aggregate.valid_days
            entry["data_points"] += aggregate.valid_days * 96
            if aggregate.valid_days:
                entry["valid_nodes"] += 1
                valid_nodes += 1
            total_days += aggregate.valid_days
            total_points += aggregate.valid_days * 96
            for item in aggregate.monthly:
                period = period_map.setdefault(item.period, {"node_count": 0, "valid_days": 0,
                                                              "spread_total": 0.0})
                period["node_count"] += 1
                period["valid_days"] += item.valid_days
                period["spread_total"] += item.spread_yuan_per_mwh * item.valid_days
        monthly = [OperationsReportPeriod(period=period, node_count=data["node_count"],
                    valid_days=data["valid_days"], average_spread_yuan_per_mwh=(
                        data["spread_total"] / data["valid_days"] if data["valid_days"] else 0.0))
                   for period, data in sorted(period_map.items())]
        provinces = [OperationsReportProvince(province=province, **data)
                     for province, data in sorted(province_map.items())]
        return OperationsReport(market=market, start_date=start_date.isoformat(), end_date=end_date.isoformat(),
                                duration_hours=duration_hours, node_count=len(nodes), valid_nodes=valid_nodes,
                                total_valid_days=total_days, total_data_points=total_points,
                                provinces=provinces, monthly=monthly, source_mode=self.data_mode)

    def portfolio_candidates(self, market: str, start_date: date, end_date: date,
                             power_mw: float = 100, capacity_mwh: float = 200,
                             round_trip_efficiency: float = 0.92,
                             unit_investment_yuan_wh: float = 1.2) -> PortfolioCandidatesResult:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date or power_mw <= 0 or capacity_mwh <= 0:
            raise ValueError("节点、规模或日期范围无效")
        duration = capacity_mwh / power_mw
        if duration < 0.25 or duration > 24 or not 0 < round_trip_efficiency <= 1:
            raise ValueError("容量/功率时长或效率无效")
        candidates = []
        for node in self.nodes()[:50]:
            aggregate = self.price_aggregates(node.id, market, start_date, end_date, duration)
            if not aggregate.annual:
                continue
            baseline = aggregate.annual[0]
            daily = max(0.0, (baseline.discharge_price_yuan_per_mwh * round_trip_efficiency
                              - baseline.charge_price_yuan_per_mwh) * capacity_mwh)
            candidates.append({
                "name": f"{node.name}·{market}", "node_id": node.id, "province": node.province,
                "market": market, "capacity_mwh": capacity_mwh,
                "unit_investment_yuan_wh": unit_investment_yuan_wh,
                "annual_revenue_wan": daily * 365 / 10000,
                "spread_yuan_per_mwh": baseline.spread_yuan_per_mwh,
                "valid_days": aggregate.valid_days, "source_mode": aggregate.source_mode,
            })
        snapshot_id = "demo"
        if self._reader:
            snapshot_id = DispatchSnapshots().put({
                "kind": "portfolio-candidates", "algorithm_version": "portfolio-candidates-v1",
                "parameters": {"market": market, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                               "power_mw": power_mw, "capacity_mwh": capacity_mwh,
                               "round_trip_efficiency": round_trip_efficiency,
                               "unit_investment_yuan_wh": unit_investment_yuan_wh},
                "candidates": candidates,
            })
        return PortfolioCandidatesResult(market=market, power_mw=power_mw, capacity_mwh=capacity_mwh,
            duration_hours=duration, round_trip_efficiency=round_trip_efficiency,
            start_date=start_date.isoformat(), end_date=end_date.isoformat(), snapshot_id=snapshot_id,
            algorithm_version="portfolio-candidates-v1", candidates=candidates)

    def portfolio_candidate_snapshot(self, snapshot_id: str) -> PortfolioCandidatesResult:
        """Read and validate an immutable real-node candidate snapshot."""
        if snapshot_id == "demo":
            raise ValueError("演示数据没有可追溯的候选快照")
        try:
            payload = DispatchSnapshots().read(snapshot_id)
        except (FileNotFoundError, IsADirectoryError, OSError) as error:
            raise ValueError("候选快照不存在") from error
        if payload.get("kind") != "portfolio-candidates":
            raise ValueError("快照类型不是候选项目")
        parameters = payload.get("parameters") or {}
        try:
            power_mw = float(parameters["power_mw"])
            capacity_mwh = float(parameters["capacity_mwh"])
            duration_hours = capacity_mwh / power_mw
            return PortfolioCandidatesResult(
                market=str(parameters["market"]), power_mw=power_mw,
                capacity_mwh=capacity_mwh, duration_hours=duration_hours,
                round_trip_efficiency=float(parameters["round_trip_efficiency"]),
                start_date=str(parameters["start_date"]), end_date=str(parameters["end_date"]),
                snapshot_id=snapshot_id, algorithm_version=str(payload.get("algorithm_version") or "unknown"),
                candidates=payload.get("candidates") or [],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("候选快照内容不完整") from error

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

    def price_aggregates(self, node_id: int, market: str, start_date: date,
                         end_date: date, duration_hours: float = 2.0) -> PriceAggregateResult:
        if market not in {"日前", "实时"}:
            raise ValueError("market must be 日前 or 实时")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        if not isfinite(duration_hours) or duration_hours < 0.25 or duration_hours > 24:
            raise ValueError("duration_hours must be between 0.25 and 24")
        slots = round(duration_hours * 4)
        if abs(duration_hours * 4 - slots) > 1e-6:
            raise ValueError("统计窗口时长须为15分钟的整数倍")
        rows = []
        if self._reader:
            try:
                # Full staging/legacy snapshots retain every source candidate,
                # which lets the aggregate expose duplicate-source dates.
                rows = [row for row in self._reader.baseline_curves(node_id, market)
                        if start_date <= date.fromisoformat(str(row["run_date"])[:10]) <= end_date]
            except (ValueError, RuntimeError):
                # Date-bounded staging samples may not have a full-history scope.
                rows = self._reader.price_curves(node_id, market, start_date, end_date)
        aggregate = aggregate_periods(rows, slots, start_date, end_date)
        return PriceAggregateResult(
            node_id=node_id, market=market, start_date=start_date, end_date=end_date,
            duration_hours=duration_hours, source_mode=self.data_mode, **aggregate,
        )

    def weather(self, node_id: int, start_time: datetime | None = None,
                end_time: datetime | None = None) -> WeatherSummary:
        if self._legacy_reader:
            observed = WeatherSummary.model_validate(
                self._legacy_reader.weather_summary(node_id, start_time, end_time)
            )
            if observed.observations:
                return observed
        if not self._reader:
            return WeatherSummary(node_id=node_id, observations=0, source_mode="unavailable")
        preset = self._preset_weather(node_id, start_time, end_time, 744)
        return WeatherSummary(
            node_id=node_id,
            start_time=preset[0]["data_time"] if preset else None,
            end_time=preset[-1]["data_time"] if preset else None,
            observations=len(preset),
            source=preset[0]["source"] if preset else None,
            avg_ghi_w_m2=_mean(preset, "ghi_w_m2"),
            avg_wind_speed_m_s=_mean(preset, "wind_speed_m_s"),
            avg_temp_c=_mean(preset, "temp_c"),
            source_mode="province-preset",
        )

    def weather_series(self, node_id: int, start_time: datetime | None = None,
                       end_time: datetime | None = None, limit: int = 744) -> list[WeatherObservation]:
        if end_time and start_time and end_time < start_time:
            raise ValueError("end_time must be on or after start_time")
        if not 1 <= limit <= 744:
            raise ValueError("limit must be between 1 and 744")
        observations = (
            self._legacy_reader.weather_observations(node_id, start_time, end_time, limit)
            if self._legacy_reader else []
        )
        source_mode = "legacy-readonly"
        if not observations and self._reader:
            observations = self._preset_weather(node_id, start_time, end_time, limit)
            source_mode = "province-preset"
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
                wind_predict_power_mw=round(wind_power, 4) if wind_power is not None else None,
                source_mode=source_mode))
        return result

    def _preset_weather(self, node_id: int, start_time: datetime | None,
                        end_time: datetime | None, limit: int) -> list[dict]:
        """Create transparent province-level display data when no observations exist."""
        start = start_time or datetime(2026, 1, 1, tzinfo=UTC)
        end = end_time or start + timedelta(days=1)
        if end < start:
            raise ValueError("end_time must be on or after start_time")
        province = self._province_for_node(node_id)
        profiles = {
            "海南": (760.0, 5.8, 25.5), "广东": (700.0, 4.8, 23.0),
            "广西": (680.0, 4.5, 22.5), "湖北": (620.0, 3.8, 16.0),
            "山西": (640.0, 4.2, 13.0), "新疆": (820.0, 3.6, 12.0),
            "甘肃": (800.0, 4.0, 11.0), "内蒙古": (760.0, 5.0, 10.0),
        }
        ghi_peak, wind_base, temp_base = profiles.get(province, (650.0, 4.2, 18.0))
        source = f"省级预设·{province}（展示数据）"
        rows: list[dict] = []
        current = start.replace(minute=0, second=0, microsecond=0)
        while current <= end and len(rows) < limit:
            hour = current.hour + current.minute / 60
            daylight = max(0.0, sin((hour - 6.0) / 12.0 * pi))
            seasonal = 1.0 + 0.1 * cos((current.timetuple().tm_yday - 172) / 365.0 * 2 * pi)
            ghi = round(ghi_peak * daylight * seasonal, 2)
            wind = round(max(0.1, wind_base + 1.2 * sin((hour + 2.0) / 24.0 * 2 * pi)), 2)
            temp = round(temp_base + 5.0 * sin((hour - 8.0) / 24.0 * 2 * pi), 2)
            rows.append({"data_time": current, "source": source,
                         "ghi_w_m2": ghi, "wind_speed_m_s": wind, "temp_c": temp})
            current += timedelta(hours=1)
        return rows

    def _province_for_node(self, node_id: int) -> str:
        if self._reader:
            try:
                rows = self._reader.list_nodes()
                for row in rows:
                    if int(row["id"]) == node_id:
                        return str(row.get("province") or "全国")
            except (KeyError, TypeError, ValueError, RuntimeError):
                pass
        return "全国"

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
        # 1.6.6 节点分析同时展示 2h/8 点与 4h/16 点连续滑动均价差。
        # 项目功率/容量仍决定财务联动采用哪一组；两组结果共享同一批有效日。
        window_baselines = []
        for window_duration in sorted({2.0, 4.0, float(duration)}):
            window = baseline if abs(window_duration - duration) <= 1e-9 else annual_window_average(
                curves, round(window_duration * 4)
            )
            window_baselines.append(PriceWindowBaseline(
                duration_hours=window_duration,
                start_date=window["start_date"], end_date=window["end_date"],
                valid_days=window["valid_days"], available_days=window["available_days"],
                excluded_records=window["excluded_records"],
                multiple_source_days=window["multiple_source_days"],
                baseline_policy=window["baseline_policy"],
                charge_price_yuan_per_mwh=window["charge_price_yuan_per_mwh"],
                discharge_price_yuan_per_mwh=window["discharge_price_yuan_per_mwh"],
                spread_yuan_per_mwh=window["spread_yuan_per_mwh"],
                monthly=[PriceBaselineMonth.model_validate(row) for row in window["monthly"]],
            ))
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
            window_baselines=window_baselines,
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


def _mean(rows: list[dict], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _wind_power(speed: float, capacity: float) -> float:
    if speed < 3 or speed >= 25:
        return 0.0
    if speed >= 12:
        return capacity
    return capacity * ((speed**3 - 3**3) / (12**3 - 3**3))
