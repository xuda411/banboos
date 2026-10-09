"""Page and filter a fixed snapshot without re-querying the price database."""
from packages.contracts.portfolio_candidates_result import PortfolioCandidatesResult


def candidate_page(snapshot: PortfolioCandidatesResult, *, offset: int = 0,
                   limit: int = 20, province: str = "", query: str = "") -> dict:
    if offset < 0 or not 1 <= limit <= 50:
        raise ValueError("分页范围无效")
    rows = sorted(snapshot.candidates, key=lambda row: (row.province, row.node_id))
    provinces = sorted({row.province for row in rows if row.province})
    rows = [row for row in rows if (not province or row.province == province)
            and (not query or query.casefold() in row.name.casefold()
                 or query == str(row.node_id))]
    return {"snapshot_id": snapshot.snapshot_id, "total": len(snapshot.candidates),
            "parameters": snapshot.model_dump(exclude={"candidates"}),
            "filtered_total": len(rows), "offset": offset, "limit": limit,
            "provinces": provinces,
            "items": [row.model_dump() for row in rows[offset:offset + limit]]}


def select_candidates(snapshot: PortfolioCandidatesResult, node_ids: list[int] | None):
    if node_ids is None:
        if len(snapshot.candidates) > 50:
            raise ValueError("快照超过50个候选，请明确选择最多50个节点后提交")
        return snapshot.candidates
    by_id = {row.node_id: row for row in snapshot.candidates}
    if not node_ids or len(node_ids) > 50 or len(set(node_ids)) != len(node_ids):
        raise ValueError("请选择1至50个不重复的候选节点")
    if any(node_id not in by_id for node_id in node_ids):
        raise ValueError("选择的节点不属于此快照")
    return [by_id[node_id] for node_id in node_ids]
