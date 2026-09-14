from packages.infrastructure.sql_models import Base


def test_server_schema_contains_tenant_station_telemetry_and_runs():
    assert set(Base.metadata.tables) == {"tenants", "stations", "telemetry_points", "run_records"}
    assert "ix_telemetry_station_event" in {
        index.name for index in Base.metadata.tables["telemetry_points"].indexes
    }
