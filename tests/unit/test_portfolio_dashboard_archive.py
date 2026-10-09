import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from packages.application.portfolio_archive import create_portfolio_archive
from packages.application.portfolio_dashboard import build_portfolio_dashboard
from packages.contracts.readonly import RunStatus
from packages.infrastructure.dispatch_snapshots import DispatchSnapshots


def _run(source_id: str) -> RunStatus:
    return RunStatus(
        run_id="11111111-1111-4111-8111-111111111111", kind="portfolio-optimization",
        status="succeeded", created_at=datetime.now(UTC), completed_at=datetime.now(UTC),
        parameters={}, result={
            "objective": "max_npv", "selected_projects": [{"name": "湖北节点", "capacity_mwh": 200,
                "investment_wan": 24000, "npv_wan": 1000, "annual_revenue_wan": 3000}],
            "total_investment_wan": 24000, "total_npv_wan": 1000,
            "total_annual_revenue_wan": 3000, "portfolio_irr": 0.12,
            "algorithm_version": "portfolio-milp-annuity-v1", "outcome": "optimal",
            "message": "完成", "cashflow_note": "历史估算",
            "candidate_source": {"snapshot_id": source_id, "algorithm_version": "test",
                "candidate_count": 1, "selected_node_ids": [1],
                "nodes": [{"name": "湖北节点", "node_id": 1, "province": "湖北"}]},
        })


def test_dashboard_groups_selected_projects_by_province():
    dashboard = build_portfolio_dashboard(_run("a" * 64))
    assert dashboard["metrics"]["selected_count"] == 1
    assert dashboard["provinces"][0]["province"] == "湖北"
    assert dashboard["candidate_source"]["candidate_count"] == 1


def test_archive_contains_manifest_and_verified_snapshot(monkeypatch):
    # Keep all generated test files on the dedicated E: volume.
    root = Path("E:/Banboos2.0/var/tests") / f"portfolio-archive-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    snapshot_root = root / "snapshots"
    monkeypatch.setenv("BANBOOS2_SNAPSHOT_DIR", str(snapshot_root))
    snapshot = {"kind": "portfolio-candidates", "algorithm_version": "test",
                "parameters": {"market": "实时"}, "candidates": [{"node_id": 1}]}
    snapshot_id = DispatchSnapshots(snapshot_root).put(snapshot)
    run = _run(snapshot_id)
    target, archive_hash = create_portfolio_archive(run, root / "archives")
    assert target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == archive_hash
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "portfolio-result.json", "candidate-snapshot.json"} <= names
        manifest = json.loads(archive.read("manifest.json"))
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
