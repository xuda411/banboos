def test_api_bootstrap_contract():
    from apps.api.main import app

    assert app.title == "Banboos 2.0 API"
    assert any(route.path == "/health" for route in app.routes)
    assert any(route.path == "/api/v1/meta" for route in app.routes)


def test_readiness_and_optional_api_token(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api import main

    client = TestClient(main.app)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.headers["X-Request-ID"]

    monkeypatch.setenv("BANBOOS2_API_TOKEN", "t" * 32)
    assert client.get("/api/v1/meta").status_code == 401
    response = client.get("/api/v1/meta", headers={"X-API-Key": "t" * 32})
    assert response.status_code == 200

    monkeypatch.delenv("BANBOOS2_API_TOKEN")
    monkeypatch.setenv("BANBOOS2_ENV", "production")
    assert client.get("/readyz").status_code == 503


def test_readonly_demo_endpoints():
    from fastapi.testclient import TestClient

    from apps.api import main

    client = TestClient(main.app)
    response = client.get("/api/v1/nodes", params={"province": "湖北"})
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "演示储能节点"

    response = client.get("/api/v1/price/summary", params={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json()["source_mode"] == "demo"

    response = client.get("/api/v1/quality/summary", params={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json()["coverage_ratio"] == 0

    response = client.get("/api/v1/price/summary", params={
        "node_id": 1, "market": "未知", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 400

    response = client.post("/api/v1/runs", json={"kind": "strict-dispatch", "parameters": {"node_id": 1}})
    assert response.status_code == 422

    response = client.post("/api/v1/runs", params={"kind": "readonly-price-analysis"})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    response = client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    first = client.post("/api/v1/runs?kind=readonly-price-analysis", headers={"Idempotency-Key": "demo-1"})
    second = client.post("/api/v1/runs?kind=readonly-price-analysis", headers={"Idempotency-Key": "demo-1"})
    assert first.json()["run_id"] == second.json()["run_id"]

    request = {
        "kind": "price-summary",
        "parameters": {
            "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
        },
    }
    response = client.post("/api/v1/runs", json=request)
    assert response.status_code == 202
    assert response.json()["parameters"] == request["parameters"]
