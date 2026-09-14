from datetime import UTC, datetime

from apps.edge.simulator import generate_batch


def test_station_simulator_emits_canonical_points():
    batch = generate_batch(at=datetime(2026, 1, 1, tzinfo=UTC))
    assert len(batch.points) == 3
    assert {point.point_id for point in batch.points} == {"soc", "active_power", "temperature"}
    assert all(point.source_protocol == "simulator" for point in batch.points)
