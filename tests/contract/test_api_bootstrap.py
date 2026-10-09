def test_api_bootstrap_contract():
    from apps.api.main import app

    assert app.title == "Banboos 2.0 API"
    assert any(route.path == "/health" for route in app.routes)
    assert any(route.path == "/api/v1/meta" for route in app.routes)
    assert any(route.path == "/api/v1/price/export" for route in app.routes)
    assert any(route.path == "/api/v1/weather/export" for route in app.routes)
    assert any(route.path == "/api/v1/price/aggregates" for route in app.routes)
    assert any(route.path == "/api/v1/runs/{run_id}/reconciliation" for route in app.routes)
    assert any(route.path == "/api/v1/runs/{run_id}/financial-reconciliation" for route in app.routes)
    assert any(route.path == "/api/v1/runs/{run_id}/financial-template-reconciliation" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates/{snapshot_id}" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates/{snapshot_id}/export" for route in app.routes)
    assert any(route.path == "/api/v1/import/preview" for route in app.routes)
    assert any(route.path == "/api/v1/import/commit" for route in app.routes)
    assert any(route.path == "/api/v1/operations/report" for route in app.routes)
    assert any(route.path == "/api/v1/operations/report/export" for route in app.routes)
    assert any(route.path == "/api/v1/price/aggregates/export" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates/export" for route in app.routes)
    assert any(route.path == "/api/v1/system/launch-gate" for route in app.routes)
    assert any(route.path == "/api/v1/system/preflight" for route in app.routes)
    assert any(route.path == "/api/v1/ems/decision-plans" for route in app.routes)
    assert any(route.path == "/api/v1/ems/feedback" for route in app.routes)
    assert any(route.path == "/api/v1/ems/dashboard" for route in app.routes)
    assert any(route.path == "/api/v1/auth/session" for route in app.routes)
    assert any(route.path == "/api/v1/auth/policy" for route in app.routes)
    assert any(route.path == "/api/v1/auth/methods" for route in app.routes)
    assert any(route.path == "/api/v1/auth/challenges" for route in app.routes)
    assert any(route.path == "/api/v1/auth/login" for route in app.routes)
    assert any(route.path == "/api/v1/admin/users" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates/{snapshot_id}/optimize" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates/snapshots" for route in app.routes)
    assert any(route.path == "/api/v1/portfolio/candidates/{snapshot_id}/page" for route in app.routes)


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
    response = client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {'t' * 32}"})
    assert response.status_code == 200
    assert response.json()["mode"] == "token"
    assert response.json()["user"]["role"] == "platform_admin"
    assert client.get("/api/v1/auth/policy", headers={"X-API-Key": "t" * 32}).json()["write_mode"] == "preview-only"

    monkeypatch.delenv("BANBOOS2_API_TOKEN")
    monkeypatch.setenv("BANBOOS2_ENV", "production")
    assert client.get("/readyz").status_code == 503


def test_production_identity_mode_never_falls_back_to_open_api(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api import main

    monkeypatch.setenv("BANBOOS2_ENV", "production")
    monkeypatch.setenv("BANBOOS2_AUTH_MODE", "identity")
    client = TestClient(main.app)

    assert client.get("/api/v1/nodes").status_code == 503
    assert client.get("/api/v1/auth/session").status_code == 503
    assert client.get("/api/v1/auth/methods").status_code == 200


def test_identity_methods_and_provider_gate():
    from fastapi.testclient import TestClient

    from apps.api import main

    client = TestClient(main.app)
    response = client.get("/api/v1/auth/methods")
    assert response.status_code == 200
    assert response.json()["default_provider"] == "phone"
    assert {item["key"] for item in response.json()["providers"]} == {"phone", "email", "wechat"}
    response = client.post("/api/v1/auth/challenges", json={
        "provider": "phone", "identifier": "13800138000", "purpose": "login",
    })
    assert response.status_code == 503
    assert "尚未配置" in response.json()["detail"]
    response = client.post("/api/v1/auth/challenges", json={
        "provider": "phone", "identifier": "123", "purpose": "login",
    })
    assert response.status_code == 422
    assert "手机号格式" in response.json()["detail"]
    response = client.get("/api/v1/admin/users")
    assert response.status_code == 200
    assert response.json()["mode"] == "preview-only"


def test_readonly_demo_endpoints():
    from fastapi.testclient import TestClient

    from apps.api import main

    client = TestClient(main.app)
    response = client.get("/api/v1/nodes", params={"province": "湖北"})
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "演示储能节点"
    response = client.get("/api/v1/legacy/import-logs")
    assert response.status_code == 200
    assert response.json() == {"items": [], "source_mode": "demo", "table": "import-logs"}
    assert client.get("/api/v1/legacy/not-a-table").status_code == 422

    response = client.get("/api/v1/price/summary", params={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json()["source_mode"] == "demo"
    response = client.get("/api/v1/weather/series", params={"node_id": 1})
    assert response.status_code == 200
    assert response.json() == []
    assert client.get("/api/v1/price/export", params={"node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31"}).status_code == 400
    assert client.get("/api/v1/weather/export", params={"node_id": 1}).status_code == 400
    response = client.get("/api/v1/price/range", params={"node_id": 1, "market": "实时"})
    assert response.status_code == 200
    assert response.json()["first_date"] is None
    response = client.get("/api/v1/price/curves", params={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json() == []
    response = client.get("/api/v1/price/aggregates", params={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json()["source_mode"] == "demo"
    assert response.json()["monthly"] == []
    assert len(response.json()["missing_dates"]) == 31
    response = client.get("/api/v1/portfolio/candidates", params={
        "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json()["candidates"] == []
    assert response.json()["snapshot_id"]
    assert client.get("/api/v1/runs/not-a-run/financial-template-reconciliation").status_code == 400

    response = client.get("/api/v1/quality/summary", params={
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 200
    assert response.json()["coverage_ratio"] == 0

    response = client.get("/api/v1/price/summary", params={
        "node_id": 1, "market": "未知", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 400

    from apps.edge.simulator import generate_batch
    batch = generate_batch()
    response = client.post("/api/v1/telemetry/batches", json=batch.model_dump(mode="json"))
    assert response.status_code == 200
    assert response.json()["accepted_points"] == 3
    assert response.json()["alerts"] == []
    response = client.post("/api/v1/telemetry/batches", json=batch.model_dump(mode="json"))
    assert response.json()["accepted_points"] == 0
    response = client.get("/api/v1/edge/gw-demo/heartbeat", params={"connected": "false"})
    assert response.json()["control_mode"] == "disabled"
    response = client.post(f"/api/v1/telemetry/batches/{batch.batch_id}/ack")
    assert response.json()["acknowledged_points"] == 3

    response = client.get("/api/v1/runs", params={"kind": "financial", "limit": 5})
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = client.post("/api/v1/runs", json={"kind": "strict-dispatch", "parameters": {"node_id": 1}})
    assert response.status_code == 422
    response = client.post("/api/v1/runs", json={"kind": "lp-analysis", "parameters": {
        "node_id": 1, "market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-01",
        "power_mw": 100, "capacity_mwh": 200,
    }})
    assert response.status_code == 202
    response = client.post("/api/v1/runs", json={"kind": "sensitivity", "parameters": {
        "base": {"power_mw": 100, "capacity_mwh": 200, "annual_revenue_yuan": 8_000_000},
        "variable": "annual_revenue_yuan", "change_rates": [-0.2, 0, 0.2],
    }})
    assert response.status_code == 202
    response = client.post("/api/v1/runs", json={"kind": "sensitivity", "parameters": {
        "base": {"power_mw": 100, "capacity_mwh": 200, "annual_revenue_yuan": 8_000_000},
        "variable": "annual_revenue_yuan", "change_rates": [0, 0],
    }})
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

    response = client.post("/api/v1/runs", json={"kind": "financial", "parameters": {
        "power_mw": 100, "capacity_mwh": 200, "annual_revenue_yuan": 8_000_000,
    }})
    assert response.status_code == 202
    financial_run_id = response.json()["run_id"]
    assert client.get(f"/api/v1/runs/{financial_run_id}/export").status_code == 409
    assert client.get("/api/v1/runs/not-a-uuid/export").status_code == 400
    response = client.post("/api/v1/runs", json={"kind": "financial", "parameters": {
        "power_mw": 100, "capacity_mwh": 200,
    }})
    assert response.status_code == 422
    response = client.post("/api/v1/runs", json={"kind": "financial", "parameters": {
        "power_mw": 100, "capacity_mwh": 200, "source_run_id": "dispatch-run-1",
    }})
    assert response.status_code == 202
    response = client.post("/api/v1/runs", json={"kind": "investment-scenario", "parameters": {
        "source_run_id": "short-source-id",
    }})
    assert response.status_code == 422
    response = client.post("/api/v1/runs", json={"kind": "investment-scenario", "parameters": {
        "source_run_id": "source-run-12345678901234567890123456789012",
        "scenario_name": "基准情景", "spread_factor": 1, "annual_cycles": 350,
        "utilization": 1, "retention_rate": 1,
    }})
    assert response.status_code == 202
