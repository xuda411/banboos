def test_api_bootstrap_contract():
    from apps.api.main import app

    assert app.title == "Banboos 2.0 API"
    assert any(route.path == "/health" for route in app.routes)
    assert any(route.path == "/api/v1/meta" for route in app.routes)
