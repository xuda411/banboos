"""Minimal API bootstrap for the Banboos 2.0 foundation milestone."""
import os
from datetime import UTC, date, datetime

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from packages.application.readonly_service import ReadonlyService
from packages.application.run_registry import RedisStateStore, RunRegistry
from packages.application.task_queue import RedisTaskQueue
from packages.contracts.readonly import DataQualitySummary, PriceSummary, RunStatus, WeatherSummary
from packages.contracts.tasks import RunRequest


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


app = FastAPI(title="Banboos 2.0 API", version="2.0.0a0")
readonly_service = ReadonlyService()
redis_url = os.getenv("BANBOOS2_REDIS_URL")
run_registry = RunRegistry(RedisTaskQueue(redis_url) if redis_url else None,
                           RedisStateStore(redis_url) if redis_url else None)

allowed_origins = [item.strip() for item in os.getenv(
    "BANBOOS2_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
).split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="banboos2-api",
        version=app.version,
        timestamp=datetime.now(UTC),
    )


@app.get("/api/v1/meta", tags=["system"])
def meta() -> dict[str, str]:
    return {"product": "Banboos", "platform": "server-web-operations", "api_version": "v1",
            "data_mode": readonly_service.data_mode}


@app.get("/api/v1/nodes", tags=["readonly"])
def nodes(province: str | None = None, q: str | None = Query(default=None, max_length=80)) -> dict:
    return {"items": [item.model_dump(mode="json") for item in readonly_service.nodes(province, q)],
            "data_mode": readonly_service.data_mode}


@app.get("/api/v1/price/summary", response_model=PriceSummary, tags=["readonly"])
def price_summary(node_id: int = Query(gt=0), market: str = Query(...),
                  start_date: date = Query(...), end_date: date = Query(...)) -> PriceSummary:
    try:
        return readonly_service.price(node_id, market, start_date, end_date)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/weather/summary", response_model=WeatherSummary, tags=["readonly"])
def weather_summary(node_id: int = Query(gt=0), start_time: datetime | None = None,
                    end_time: datetime | None = None) -> WeatherSummary:
    try:
        return readonly_service.weather(node_id, start_time, end_time)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/quality/summary", response_model=DataQualitySummary, tags=["readonly"])
def quality_summary(node_id: int = Query(gt=0), market: str = Query(...),
                   start_date: date = Query(...), end_date: date = Query(...)) -> DataQualitySummary:
    try:
        return readonly_service.quality(node_id, market, start_date, end_date)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/v1/runs", response_model=RunStatus, status_code=202, tags=["runs"])
def submit_run(kind: str | None = Query(default=None, min_length=1, max_length=80),
               request: RunRequest | None = Body(default=None),
               idempotency_key: str | None = Header(default=None, alias="Idempotency-Key",
                                                    max_length=160)) -> RunStatus:
    resolved_kind = request.kind if request else kind
    if not resolved_kind:
        raise HTTPException(status_code=422, detail="kind is required")
    return run_registry.submit(resolved_kind, idempotency_key,
                               request.parameters if request else {})


@app.get("/api/v1/runs/{run_id}", response_model=RunStatus, tags=["runs"])
def get_run(run_id: str) -> RunStatus:
    item = run_registry.get(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@app.post("/api/v1/runs/{run_id}/cancel", response_model=RunStatus, tags=["runs"])
def cancel_run(run_id: str) -> RunStatus:
    item = run_registry.cancel(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="run not found")
    return item
