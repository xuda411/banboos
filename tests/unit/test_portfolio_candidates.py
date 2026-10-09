from datetime import date

import pytest

from packages.application.readonly_service import ReadonlyService
from tests.unit.test_legacy_reader import make_fixture


def test_portfolio_candidates_are_derived_from_real_node_curves(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    result = ReadonlyService(str(db)).portfolio_candidates("实时", date(2026, 1, 1), date(2026, 1, 1))
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.node_id == 1
    assert candidate.market == "实时"
    assert candidate.valid_days == 1
    assert candidate.annual_revenue_wan >= 0
    assert result.snapshot_id
    assert result.algorithm_version == "portfolio-candidates-v1"
    restored = ReadonlyService(str(db)).portfolio_candidate_snapshot(result.snapshot_id)
    assert restored.snapshot_id == result.snapshot_id
    assert restored.candidates[0].node_id == candidate.node_id


def test_portfolio_candidates_require_quarter_hour_duration(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    with pytest.raises(ValueError, match="15"):
        ReadonlyService(str(db)).portfolio_candidates(
            "实时", date(2026, 1, 1), date(2026, 1, 1), power_mw=100, capacity_mwh=201
        )
