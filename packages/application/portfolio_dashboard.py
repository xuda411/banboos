"""Traceable summary DTOs for a completed portfolio optimization run."""
from __future__ import annotations

from collections import defaultdict

from packages.contracts.readonly import RunStatus


def build_portfolio_dashboard(run: RunStatus) -> dict:
    if run.kind != "portfolio-optimization":
        raise ValueError("仅支持组合优化任务")
    if run.status != "succeeded" or not run.result:
        raise ValueError("组合任务尚未成功完成")
    result = run.result
    source = result.get("candidate_source") or run.parameters.get("candidate_source") or {}
    nodes = source.get("nodes") if isinstance(source, dict) else []
    nodes = nodes if isinstance(nodes, list) else []
    provinces: dict[str, dict] = defaultdict(lambda: {
        "province": "未标注", "selected_count": 0, "capacity_mwh": 0.0,
        "investment_wan": 0.0, "annual_revenue_wan": 0.0,
    })
    selected = result.get("selected_projects") or []
    source_by_name = {str(node.get("name")): node for node in nodes if isinstance(node, dict)}
    for project in selected:
        if not isinstance(project, dict):
            continue
        source_node = source_by_name.get(str(project.get("name")), {})
        province = str(source_node.get("province") or "未标注")
        row = provinces[province]
        row["province"] = province
        row["selected_count"] += 1
        row["capacity_mwh"] += float(project.get("capacity_mwh") or 0)
        row["investment_wan"] += float(project.get("investment_wan") or 0)
        row["annual_revenue_wan"] += float(project.get("annual_revenue_wan") or 0)
    source_nodes = [node for node in nodes if isinstance(node, dict)]
    return {
        "run_id": run.run_id,
        "status": run.status,
        "completed_at": run.completed_at,
        "algorithm_version": result.get("algorithm_version"),
        "objective": result.get("objective"),
        "outcome": result.get("outcome"),
        "message": result.get("message", run.message),
        "cashflow_note": result.get("cashflow_note"),
        "candidate_source": {
            "snapshot_id": source.get("snapshot_id"),
            "algorithm_version": source.get("algorithm_version"),
            "candidate_count": int(source.get("candidate_count") or len(source_nodes)),
            "selected_node_ids": source.get("selected_node_ids") or [],
        },
        "metrics": {
            "selected_count": len(selected),
            "total_investment_wan": float(result.get("total_investment_wan") or 0),
            "total_npv_wan": float(result.get("total_npv_wan") or 0),
            "total_annual_revenue_wan": float(result.get("total_annual_revenue_wan") or 0),
            "portfolio_irr": result.get("portfolio_irr"),
        },
        "provinces": sorted(provinces.values(), key=lambda row: (-row["investment_wan"], row["province"])),
    }
