def test_api_bootstrap_contract():
    from apps.api.main import app

    assert app.title == "Banboos 2.0 API"
    assert any(route.path == "/health" for route in app.routes)
    assert any(route.path == "/api/v1/meta" for route in app.routes)


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

    response = client.get("/api/v1/price/summary", params={
        "node_id": 1, "market": "未知", "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert response.status_code == 400

    response = client.post("/api/v1/runs", params={"kind": "readonly-price-analysis"})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    response = client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
