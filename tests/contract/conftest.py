"""Keep API tests independent of the user's running manual-check environment."""
import pytest


@pytest.fixture(autouse=True)
def isolated_api(monkeypatch, tmp_path):
    monkeypatch.setenv("BANBOOS2_ENV", "development")
    for name in ("BANBOOS2_API_TOKEN", "BANBOOS2_REDIS_URL", "BANBOOS2_LEGACY_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BANBOOS2_LOCAL_STATE", str(tmp_path / "runtime.sqlite"))
    monkeypatch.setenv("BANBOOS2_EDGE_SPOOL", str(tmp_path / "edge.sqlite"))

    from apps.api import main
    from apps.edge.gateway import TelemetrySpool
    from packages.application.readonly_service import ReadonlyService
    from packages.application.run_registry import RunRegistry
    from packages.application.sqlite_runtime import SQLiteRuntime

    runtime = SQLiteRuntime(tmp_path / "runtime.sqlite")
    monkeypatch.setattr(main, "readonly_service", ReadonlyService())
    monkeypatch.setattr(main, "redis_url", None)
    monkeypatch.setattr(main, "local_runtime", runtime)
    monkeypatch.setattr(main, "run_registry", RunRegistry(queue=runtime, store=runtime))
    monkeypatch.setattr(main, "edge_spool", TelemetrySpool(tmp_path / "edge.sqlite"))
