"""Minimal API bootstrap for the Banboos 2.0 foundation milestone."""
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


app = FastAPI(title="Banboos 2.0 API", version="2.0.0a0")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="banboos2-api",
        version=app.version,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/api/v1/meta", tags=["system"])
def meta() -> dict[str, str]:
    return {"product": "Banboos", "platform": "server-web-operations", "api_version": "v1"}
