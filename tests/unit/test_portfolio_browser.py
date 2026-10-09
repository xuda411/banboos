from datetime import date

import pytest

from packages.application.portfolio_browser import candidate_page, select_candidates
from packages.application.readonly_service import ReadonlyService
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots
from packages.infrastructure.portfolio_catalog import PortfolioCatalog
from tests.unit.test_legacy_reader import make_fixture


def test_candidate_page_filters_and_selects_by_node_id(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    make_fixture(db)
    snapshot = ReadonlyService(str(db)).portfolio_candidates("实时", date(2026, 1, 1), date(2026, 1, 1))
    page = candidate_page(snapshot, province="湖北", query="1", limit=20)
    assert page["filtered_total"] == 1
    assert page["items"][0]["node_id"] == 1
    assert select_candidates(snapshot, [1])[0].node_id == 1


def test_select_candidates_requires_explicit_selection_for_large_snapshot():
    class Item:
        node_id = 1

    class Snapshot:
        candidates = [Item()] * 51

    with pytest.raises(ValueError, match="明确选择"):
        select_candidates(Snapshot(), None)


def test_portfolio_catalog_rebuilds_from_immutable_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("BANBOOS2_SNAPSHOT_DIR", str(tmp_path))
    snapshot_id = DispatchSnapshots().put({
        "kind": "portfolio-candidates", "algorithm_version": "test",
        "parameters": {"market": "实时", "start_date": "2026-01-01", "end_date": "2026-01-01"},
        "candidates": [{"node_id": 1}],
    })
    catalog = PortfolioCatalog()
    assert catalog.page()["total"] == 1
    assert catalog.page()["items"][0]["snapshot_id"] == snapshot_id
