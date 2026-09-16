"""Read-only price adapter for successful staging-v2 migrations."""
import json
from contextlib import closing
from datetime import date

from packages.infrastructure.legacy_sqlite import LegacyDatabaseError, LegacySQLiteReader


class StagingSQLiteReader(LegacySQLiteReader):
    source_mode = "staging-readonly"

    def __init__(self, path):
        super().__init__(path)
        with closing(self._connect()) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='staging_meta'").fetchone():
                raise LegacyDatabaseError("staging 版本过旧，请重新迁移")
            self.metadata = dict(c.execute("SELECT key,value FROM staging_meta"))
            if self.metadata.get("format_version") != "2":
                raise LegacyDatabaseError("不支持的 staging 版本")

    def list_nodes(self, province=None, query=None):
        clauses = ["EXISTS (SELECT 1 FROM raw_price_records r JOIN migration_batches b USING(batch_id) WHERE r.node_id=n.id AND b.status='succeeded')"]
        params = []
        if province:
            clauses.append("n.province=?"); params.append(province)
        if query:
            clauses.append("n.node_name LIKE ?"); params.append(f"%{query}%")
        with closing(self._connect()) as c:
            rows = c.execute("SELECT n.id,n.node_name AS name,COALESCE(n.province,'') AS province FROM staging_nodes n WHERE " + " AND ".join(clauses) + " ORDER BY province,name", params).fetchall()
        return [dict(r) for r in rows]

    def node_count(self):
        return len(self.list_nodes())

    def price_curves(self, node_id, market, start_date, end_date):
        if market not in {"日前", "实时"} or end_date < start_date:
            raise ValueError("市场或日期范围无效")
        with closing(self._connect()) as c:
            rows = c.execute("SELECT c.run_date,c.prices_json,c.source_file FROM canonical_price_curves c JOIN migration_batches b USING(batch_id) WHERE b.status='succeeded' AND c.node_id=? AND c.market=? AND c.run_date>=? AND c.run_date<=? ORDER BY c.run_date", (node_id, market, start_date.isoformat(), end_date.isoformat())).fetchall()
        return [dict(run_date=r[0], prices=json.loads(r[1]), source_file=r[2]) for r in rows]

    def price_summary(self, node_id, market, start_date, end_date):
        rows = self.price_curves(node_id, market, start_date, end_date)
        return dict(node_id=node_id, market=market, start_date=start_date, end_date=end_date,
                    valid_days=len(rows), data_points=len(rows)*96,
                    first_date=rows[0]['run_date'] if rows else None,
                    last_date=rows[-1]['run_date'] if rows else None,
                    sources=sorted({r['source_file'] for r in rows if r['source_file']}),
                    source_mode=self.source_mode)

    def price_range(self, node_id, market):
        rows = self.price_summary(node_id, market, date.min, date.max)
        return {k: rows[k] for k in ('node_id','market','first_date','last_date','source_mode')}

    def quality_summary(self, node_id, market, start_date, end_date):
        if market not in {"日前", "实时"} or end_date < start_date:
            raise ValueError("市场或日期范围无效")
        with closing(self._connect()) as c:
            r = c.execute("SELECT COUNT(*),COALESCE(SUM(is_complete),0),COALESCE(SUM(missing_cells),0),COALESCE(SUM(non_finite_cells),0) FROM quality_price_records q JOIN migration_batches b USING(batch_id) WHERE b.status='succeeded' AND q.node_id=? AND q.market=? AND q.run_date>=? AND q.run_date<=?", (node_id,market,start_date.isoformat(),end_date.isoformat())).fetchone()
        return dict(node_id=node_id,market=market,start_date=start_date,end_date=end_date,
                    total_records=r[0],complete_records=r[1],incomplete_records=r[0]-r[1],
                    missing_cells=r[2],non_finite_cells=r[3],coverage_ratio=r[1]/r[0] if r[0] else 0,
                    source_mode=self.source_mode)

    def baseline_curves(self, node_id, market):
        if market not in {"日前", "实时"}:
            raise ValueError("market 必须是 日前 或 实时")
        with closing(self._connect()) as c:
            scopes = [json.loads(r[0]) for r in c.execute("SELECT scope_json FROM migration_scopes JOIN migration_batches USING(batch_id) WHERE status='succeeded'")]
            # A full-history scope includes all source candidates and missing days.
            # Date-bounded samples must never masquerade as an annual baseline.
            complete = any(s['node_id'] in (None,node_id) and s['market'] in (None,market)
                           and s['start_date'] is None and s['end_date'] is None for s in scopes)
            if not complete:
                raise ValueError("该节点市场仅迁移了部分日期，请先完成全历史批次再计算年度基准")
            rows = c.execute("SELECT r.run_date,r.prices_json FROM raw_price_records r JOIN migration_batches b USING(batch_id) WHERE b.status='succeeded' AND r.node_id=? AND r.market=? ORDER BY r.run_date,r.source_row_id", (node_id,market)).fetchall()
        return [dict(run_date=r[0],prices=json.loads(r[1])) for r in rows]
