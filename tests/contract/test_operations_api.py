import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from apps.edge.simulator import generate_batch


def test_operations_summary_empty_and_live_counts():
    from apps.api import main

    client = TestClient(main.app)
    response = client.get("/api/v1/operations/summary")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["schema_version"] == "v1"
    assert body["scope"] == "configured-runtime"
    assert body["node_count"] == 2
    assert body["task_counts"]["total"] == 0
    assert body["telemetry"]["pending_points"] == 0
    assert body["alerts"]["unacknowledged"] == 0
    assert body["control_mode"] == "disabled"

    client.post("/api/v1/runs?kind=readonly-price-analysis")
    batch = generate_batch()
    batch.points[0].value = 106
    ingested = client.post("/api/v1/telemetry/batches", json=batch.model_dump(mode="json"))
    assert ingested.status_code == 200
    body = client.get("/api/v1/operations/summary").json()
    assert body["task_counts"]["by_status"]["queued"] == 1
    assert body["telemetry"]["pending_points"] == 3
    assert body["telemetry"]["pending_batches"] == 1
    assert body["alerts"]["unacknowledged_critical"] == 1

    client.post(f"/api/v1/telemetry/batches/{batch.batch_id}/ack")
    alert_id = ingested.json()["alerts"][0]["alert_id"]
    client.post(f"/api/v1/alerts/{alert_id}/ack")
    body = client.get("/api/v1/operations/summary").json()
    assert body["telemetry"]["acknowledged_points"] == 3
    assert body["telemetry"]["pending_batches"] == 0
    assert body["alerts"]["unacknowledged"] == 0
    assert body["alerts"]["acknowledged"] == 1


@pytest.mark.parametrize(("target", "method", "component"), [
    ("readonly_service", "node_count", "nodes"),
    ("run_registry", "status_counts", "tasks"),
    ("edge_spool", "operations_counts", "telemetry"),
])
def test_operations_unavailable_has_safe_retry_response(monkeypatch, target, method, component):
    from apps.api import main

    def fail():
        raise sqlite3.OperationalError("secret database path")

    monkeypatch.setattr(getattr(main, target), method, fail)
    response = TestClient(main.app).get("/api/v1/operations/summary")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]
    assert response.json()["detail"]["component"] == component
    assert response.json()["detail"]["code"] == "OPERATIONS_SUMMARY_UNAVAILABLE"
    assert "secret" not in response.text


def test_operations_summary_uses_existing_api_auth(monkeypatch):
    from apps.api import main

    monkeypatch.setenv("BANBOOS2_API_TOKEN", "t" * 32)
    client = TestClient(main.app)
    assert client.get("/api/v1/operations/summary").status_code == 401
    assert client.get("/api/v1/operations/summary", headers={"X-API-Key": "t" * 32}).status_code == 200


def test_pending_api_limit_counts_whole_batches():
    from apps.api import main

    client = TestClient(main.app)
    earlier = generate_batch(at=datetime(2026, 1, 1, tzinfo=UTC))
    later = generate_batch(at=datetime(2026, 1, 2, tzinfo=UTC))
    for batch in (later, earlier):
        assert client.post("/api/v1/telemetry/batches", json=batch.model_dump(mode="json")).status_code == 200
    response = client.get("/api/v1/telemetry/pending?limit=1")
    assert response.status_code == 200
    body = response.json()
    assert body["pending_points"] == 6
    assert len(body["items"]) == 1
    assert body["items"][0]["batch_id"] == earlier.batch_id
    assert body["items"][0]["points"] == 3
    client.post(f"/api/v1/telemetry/batches/{earlier.batch_id}/ack")
    body = client.get("/api/v1/telemetry/pending?limit=1").json()
    assert body["pending_points"] == 3
    assert body["items"][0]["batch_id"] == later.batch_id
    assert body["items"][0]["points"] == 3
