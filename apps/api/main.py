"""Minimal API bootstrap for the Banboos 2.0 foundation milestone."""
import logging
import os
import re
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import redis
from fastapi import Body, FastAPI, Header, HTTPException, Query, Response
from fastapi import Path as APIPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from apps.api.security import configured_token, is_production, token_matches
from apps.edge.gateway import TelemetrySpool
from packages.application.financial_export import export_financial_xlsx
from packages.application.financial_template_xlsm import export_financial_xlsm
from packages.application.operations_service import OperationsService, OperationsUnavailable
from packages.application.readonly_service import ReadonlyService
from packages.application.report_export import (
    SUPPORTED_TASKS,
    export_price_xlsx,
    export_task_xlsx,
    export_weather_xlsx,
)
from packages.application.run_registry import RedisStateStore, RunRegistry
from packages.application.sqlite_runtime import SQLiteRuntime, runtime_path
from packages.application.task_queue import RedisTaskQueue
from packages.contracts.dispatch import DispatchParameters
from packages.contracts.financial import FinancialTaskParameters
from packages.contracts.financial_reconciliation import FinancialReconciliationResult
from packages.contracts.investment_scenario import InvestmentScenarioParameters
from packages.contracts.lp_analysis import LPAnalysisParameters
from packages.contracts.lp_reconciliation import LPReconciliationResult
from packages.contracts.operations import OperationsSummary
from packages.contracts.portfolio import PortfolioTaskParameters
from packages.contracts.portfolio_candidates_result import PortfolioCandidatesResult
from packages.contracts.readonly import (
    DataQualitySummary,
    PriceAggregateResult,
    PriceCurve,
    PriceRange,
    PriceSummary,
    RunStatus,
    WeatherObservation,
    WeatherSummary,
)
from packages.contracts.sensitivity import SensitivityTaskParameters
from packages.contracts.tasks import RunRequest
from packages.contracts.telemetry import TelemetryAlert, TelemetryBatch, TelemetryPoint
from packages.domain.telemetry_alerts import evaluate_alerts


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


app = FastAPI(title="Banboos 2.0 API", version="2.0.0a0")
readonly_service = ReadonlyService()
redis_url = os.getenv("BANBOOS2_REDIS_URL")
local_runtime = SQLiteRuntime(runtime_path()) if not redis_url else None
run_registry = RunRegistry(RedisTaskQueue(redis_url) if redis_url else local_runtime,
                           RedisStateStore(redis_url) if redis_url else local_runtime)
edge_spool = TelemetrySpool(os.getenv("BANBOOS2_EDGE_SPOOL", "var/edge/telemetry.sqlite"))

allowed_origins = [item.strip() for item in os.getenv(
    "BANBOOS2_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
).split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.middleware("http")
async def request_guard(request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    protected = request.url.path.startswith("/api/")
    candidate = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if protected and configured_token() and not token_matches(candidate or request.headers.get("X-API-Key")):
        response = JSONResponse({"detail": "authentication required"}, status_code=401)
        response.headers["X-Request-ID"] = request_id
        return response
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="banboos2-api",
        version=app.version,
        timestamp=datetime.now(UTC),
    )


@app.get("/readyz", tags=["system"])
def ready() -> dict:
    checks = {"api": "ok", "redis": "not-configured", "auth": "ok"}
    if is_production() and (not configured_token() or len(configured_token() or "") < 32):
        checks["auth"] = "production token must be at least 32 characters"
    if redis_url:
        try:
            redis.Redis.from_url(redis_url, decode_responses=True).ping()
            checks["redis"] = "ok"
        except redis.RedisError:
            checks["redis"] = "unavailable"
    ready_state = all(value in {"ok", "not-configured"} for value in checks.values())
    if not ready_state:
        raise HTTPException(status_code=503, detail={"status": "not-ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@app.get("/api/v1/meta", tags=["system"])
def meta() -> dict[str, str]:
    template = os.getenv("BANBOOS2_FINANCIAL_TEMPLATE")
    template_available = bool(template and Path(template).expanduser().is_file()
                              and Path(template).suffix.lower() == ".xlsm")
    return {"product": "Banboos", "platform": "server-web-operations", "api_version": "v1",
            "data_mode": readonly_service.data_mode,
            "financial_template_available": str(template_available)}


@app.get("/api/v1/nodes", tags=["readonly"])
def nodes(province: str | None = None, q: str | None = Query(default=None, max_length=80)) -> dict:
    return {"items": [item.model_dump(mode="json") for item in readonly_service.nodes(province, q)],
            "data_mode": readonly_service.data_mode}


@app.get("/api/v1/legacy/{kind}", tags=["legacy-readonly"])
def legacy_management(kind: str = APIPath(..., pattern="^(import-logs|field-mappings|breakpoints|geo-mappings|province-investment|access-log)$"),
                      limit: int = Query(default=200, ge=1, le=200)) -> dict:
    """Expose 1.6.6 management metadata without exposing any write operation."""
    try:
        return readonly_service.legacy_management(kind, limit)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/operations/summary", response_model=OperationsSummary, tags=["operations"])
def operations_summary(response: Response) -> OperationsSummary:
    response.headers["Cache-Control"] = "no-store"
    try:
        return OperationsService(readonly_service, run_registry, edge_spool).summary()
    except OperationsUnavailable as error:
        logging.getLogger("banboos2.api").warning(
            "operations summary unavailable", extra={"component": error.component}
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "OPERATIONS_SUMMARY_UNAVAILABLE", "component": error.component,
                    "message": "运营摘要暂不可用，请稍后重试"},
            headers={"Retry-After": "5", "Cache-Control": "no-store"},
        ) from error


@app.get("/api/v1/price/summary", response_model=PriceSummary, tags=["readonly"])
def price_summary(node_id: int = Query(gt=0), market: str = Query(...),
                  start_date: date = Query(...), end_date: date = Query(...)) -> PriceSummary:
    try:
        return readonly_service.price(node_id, market, start_date, end_date)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/price/range", response_model=PriceRange, tags=["readonly"])
def price_range(node_id: int = Query(gt=0), market: str = Query(...)) -> PriceRange:
    try:
        return readonly_service.price_range(node_id, market)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/price/curves", response_model=list[PriceCurve], tags=["readonly"])
def price_curves(node_id: int = Query(gt=0), market: str = Query(...),
                 start_date: date = Query(...), end_date: date = Query(...),
                 limit: int = Query(default=31, ge=1, le=31)) -> list[PriceCurve]:
    try:
        return readonly_service.curves(node_id, market, start_date, end_date, limit)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/price/aggregates", response_model=PriceAggregateResult, tags=["readonly"])
def price_aggregates(node_id: int = Query(gt=0), market: str = Query(...),
                     start_date: date = Query(...), end_date: date = Query(...),
                     duration_hours: float = Query(default=2.0, gt=0, le=24)) -> PriceAggregateResult:
    try:
        return readonly_service.price_aggregates(node_id, market, start_date, end_date, duration_hours)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/portfolio/candidates", response_model=PortfolioCandidatesResult, tags=["readonly"])
def portfolio_candidates(market: str = Query(...), start_date: date = Query(...), end_date: date = Query(...),
                          power_mw: float = Query(default=100, gt=0), capacity_mwh: float = Query(default=200, gt=0),
                          round_trip_efficiency: float = Query(default=0.92, gt=0, le=1),
                          unit_investment_yuan_wh: float = Query(default=1.2, gt=0)) -> PortfolioCandidatesResult:
    try:
        return readonly_service.portfolio_candidates(market, start_date, end_date, power_mw, capacity_mwh,
                                                      round_trip_efficiency, unit_investment_yuan_wh)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/portfolio/candidates/{snapshot_id}", response_model=PortfolioCandidatesResult, tags=["readonly"])
def portfolio_candidate_snapshot(snapshot_id: str = APIPath(..., min_length=64, max_length=64,
                                                               pattern=r"^[0-9a-f]{64}$")) -> PortfolioCandidatesResult:
    try:
        return readonly_service.portfolio_candidate_snapshot(snapshot_id)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/weather/summary", response_model=WeatherSummary, tags=["readonly"])
def weather_summary(node_id: int = Query(gt=0), start_time: datetime | None = None,
                    end_time: datetime | None = None) -> WeatherSummary:
    try:
        return readonly_service.weather(node_id, start_time, end_time)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/weather/series", response_model=list[WeatherObservation], tags=["readonly"])
def weather_series(node_id: int = Query(gt=0), start_time: datetime | None = None,
                  end_time: datetime | None = None,
                  limit: int = Query(default=744, ge=1, le=744)) -> list[WeatherObservation]:
    try:
        return readonly_service.weather_series(node_id, start_time, end_time, limit)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/quality/summary", response_model=DataQualitySummary, tags=["readonly"])
def quality_summary(node_id: int = Query(gt=0), market: str = Query(...),
                   start_date: date = Query(...), end_date: date = Query(...)) -> DataQualitySummary:
    try:
        return readonly_service.quality(node_id, market, start_date, end_date)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/v1/telemetry/batches", tags=["edge"])
def ingest_telemetry(batch: TelemetryBatch) -> dict:
    accepted = edge_spool.ingest(batch)
    alerts = [alert.model_copy(update={
        "alert_id": sha256(f"{batch.batch_id}:{alert.code}:{alert.device_id}:{alert.point_id}".encode()).hexdigest(),
        "batch_id": batch.batch_id, "created_at": datetime.now(UTC),
    }) for alert in evaluate_alerts(batch)]
    edge_spool.record_alerts(alerts)
    return {"batch_id": batch.batch_id, "accepted_points": accepted,
            "pending_points": edge_spool.pending_count(),
            "alerts": [alert.model_dump(mode="json") for alert in alerts],
            "control_mode": "disabled"}


@app.get("/api/v1/alerts", response_model=list[TelemetryAlert], tags=["edge"])
def list_alerts(unacknowledged_only: bool = False,
                limit: int = Query(default=100, ge=1, le=200)) -> list[TelemetryAlert]:
    return edge_spool.alerts(limit=limit, unacknowledged_only=unacknowledged_only)


@app.post("/api/v1/alerts/{alert_id}/ack", tags=["edge"])
def acknowledge_alert(alert_id: str = APIPath(..., min_length=8, max_length=128)) -> dict:
    return {"alert_id": alert_id, "acknowledged": edge_spool.ack_alert(alert_id),
            "control_mode": "disabled"}


@app.post("/api/v1/telemetry/batches/{batch_id}/ack", tags=["edge"])
def acknowledge_telemetry(batch_id: str = APIPath(..., min_length=1, max_length=160)) -> dict:
    acknowledged = edge_spool.ack(batch_id)
    return {"batch_id": batch_id, "acknowledged_points": acknowledged,
            "pending_points": edge_spool.pending_count(), "control_mode": "disabled"}


@app.get("/api/v1/telemetry/pending", tags=["edge"])
def pending_telemetry(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of complete batches"),
) -> dict:
    batches = edge_spool.pending(limit=limit)
    return {"items": [{"batch_id": batch.batch_id, "points": len(batch.points),
                       "first_event_time": min(point.event_time for point in batch.points),
                       "last_event_time": max(point.event_time for point in batch.points)}
                      for batch in batches],
            "pending_points": edge_spool.pending_count(), "control_mode": "disabled"}


@app.get("/api/v1/telemetry/recent", response_model=list[TelemetryPoint], tags=["edge"])
def recent_telemetry(station_id: str | None = Query(default=None, max_length=120),
                     device_id: str | None = Query(default=None, max_length=120),
                     point_id: str | None = Query(default=None, max_length=120),
                     limit: int = Query(default=100, ge=1, le=500)) -> list[TelemetryPoint]:
    return edge_spool.recent(station_id, device_id, point_id, limit)


@app.get("/api/v1/edge/{gateway_id}/heartbeat", tags=["edge"])
def edge_heartbeat(gateway_id: str = APIPath(..., min_length=1, max_length=120),
                   connected: bool = True) -> dict:
    return edge_spool.heartbeat(gateway_id, connected)


@app.post("/api/v1/runs", response_model=RunStatus, status_code=202, tags=["runs"])
def submit_run(kind: str | None = Query(default=None, min_length=1, max_length=80),
               request: RunRequest | None = Body(default=None),
               idempotency_key: str | None = Header(default=None, alias="Idempotency-Key",
                                                    max_length=160)) -> RunStatus:
    resolved_kind = request.kind if request else kind
    if not resolved_kind:
        raise HTTPException(status_code=422, detail="kind is required")
    if resolved_kind == "strict-dispatch":
        try:
            DispatchParameters.model_validate(request.parameters if request else {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if resolved_kind == "lp-analysis":
        try:
            LPAnalysisParameters.model_validate(request.parameters if request else {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if resolved_kind == "financial":
        try:
            FinancialTaskParameters.model_validate(request.parameters if request else {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if resolved_kind == "investment-scenario":
        try:
            InvestmentScenarioParameters.model_validate(request.parameters if request else {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if resolved_kind == "sensitivity":
        try:
            SensitivityTaskParameters.model_validate(request.parameters if request else {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if resolved_kind == "portfolio-optimization":
        try:
            PortfolioTaskParameters.model_validate(request.parameters if request else {})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    return run_registry.submit(resolved_kind, idempotency_key,
                               request.parameters if request else {})


@app.get("/api/v1/runs", response_model=list[RunStatus], tags=["runs"])
def list_runs(kind: str | None = Query(default=None, max_length=80),
              status: str | None = Query(default=None, max_length=24),
              limit: int = Query(default=50, ge=1, le=100)) -> list[RunStatus]:
    return run_registry.list(kind=kind, status=status, limit=limit)


@app.get("/api/v1/runs/{run_id}", response_model=RunStatus, tags=["runs"])
def get_run(run_id: str) -> RunStatus:
    item = run_registry.get(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@app.get("/api/v1/runs/{run_id}/reconciliation", response_model=LPReconciliationResult, tags=["reports"])
def reconcile_run(run_id: str) -> LPReconciliationResult:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", run_id):
        raise HTTPException(status_code=400, detail="invalid run id")
    item = run_registry.get(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    if item.kind != "lp-analysis":
        raise HTTPException(status_code=400, detail="only lp-analysis runs support reconciliation")
    if item.status != "succeeded" or not item.result:
        raise HTTPException(status_code=409, detail="run has not succeeded")
    from packages.domain.lp_reconciliation import reconcile_lp
    report = reconcile_lp(item.result)
    return LPReconciliationResult(run_id=run_id, **report)


@app.get("/api/v1/runs/{run_id}/financial-reconciliation", response_model=FinancialReconciliationResult, tags=["reports"])
def reconcile_financial_run(run_id: str) -> FinancialReconciliationResult:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", run_id):
        raise HTTPException(status_code=400, detail="invalid run id")
    item = run_registry.get(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    if item.kind != "financial":
        raise HTTPException(status_code=400, detail="only financial runs support financial reconciliation")
    if item.status != "succeeded" or not item.result:
        raise HTTPException(status_code=409, detail="run has not succeeded")
    from packages.domain.financial_reconciliation import reconcile_financial
    report = reconcile_financial(item.result, item.parameters)
    return FinancialReconciliationResult(run_id=run_id, **report)


@app.post("/api/v1/runs/{run_id}/cancel", response_model=RunStatus, tags=["runs"])
def cancel_run(run_id: str) -> RunStatus:
    item = run_registry.cancel(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@app.get("/api/v1/runs/{run_id}/export", tags=["reports"])
def export_run(run_id: str, output_format: str = Query(default="xlsx", alias="format")):
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", run_id):
        raise HTTPException(status_code=400, detail="invalid run id")
    item = run_registry.get(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    if item.kind not in SUPPORTED_TASKS or item.status != "succeeded" or not item.result:
        raise HTTPException(status_code=409, detail="支持的任务必须计算成功后才能导出")
    normalized_format = output_format.lower().strip()
    if normalized_format not in {"xlsx", "xlsm"}:
        raise HTTPException(status_code=400, detail="format 仅支持 xlsx 或 xlsm")
    if normalized_format == "xlsm" and item.kind != "financial":
        raise HTTPException(status_code=400, detail="xlsm 模板仅支持财务测算任务")
    if item.kind != "financial":
        return xlsx_response(export_task_xlsx(item), f"{item.kind}-{run_id}.xlsx")
    if normalized_format == "xlsm":
        template = os.getenv("BANBOOS2_FINANCIAL_TEMPLATE")
        if not template:
            raise HTTPException(
                status_code=503,
                detail="未配置 BANBOOS2_FINANCIAL_TEMPLATE，暂不能导出原版 XLSM 模板",
            )
        destination = Path(os.getenv("BANBOOS2_EXPORT_DIR", "var/exports")) / f"financial-{run_id}.xlsm"
        try:
            path = export_financial_xlsm(
                item.result | {"run_id": run_id, "completed_at": str(item.completed_at)},
                destination,
                template,
            )
        except (FileNotFoundError, OSError, ValueError, KeyError, RuntimeError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return FileResponse(
            path,
            media_type="application/vnd.ms-excel.sheet.macroEnabled.12",
            filename=path.name,
        )
    destination = Path(os.getenv("BANBOOS2_EXPORT_DIR", "var/exports")) / f"financial-{run_id}.xlsx"
    path = export_financial_xlsx(item.result | {"run_id": run_id, "completed_at": str(item.completed_at)}, destination)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=path.name)


def xlsx_response(content: bytes, filename: str):
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@app.get("/api/v1/price/export", tags=["reports"])
def export_price(node_id: int = Query(gt=0), market: str = Query(...),
                 start_date: date = Query(...), end_date: date = Query(...),
                 limit: int = Query(default=31, ge=1, le=31)):
    try:
        curves = readonly_service.curves(node_id, market, start_date, end_date, limit)
        content = export_price_xlsx(curves, {"节点 ID": node_id, "市场": market,
            "查询开始日期": start_date, "查询结束日期": end_date, "最大曲线日数": limit})
        return xlsx_response(content, f"price-{node_id}-{start_date}-{end_date}.xlsx")
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/weather/export", tags=["reports"])
def export_weather(node_id: int = Query(gt=0), start_time: datetime | None = None,
                   end_time: datetime | None = None, limit: int = Query(default=744, ge=1, le=744)):
    try:
        series = readonly_service.weather_series(node_id, start_time, end_time, limit)
        content = export_weather_xlsx(series, {"节点 ID": node_id, "查询开始": str(start_time),
            "查询结束": str(end_time), "最大观测数": limit})
        return xlsx_response(content, f"weather-{node_id}.xlsx")
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
