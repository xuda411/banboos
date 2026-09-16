"""Compare source rows, Canonical values and 2h/4h baselines in a bounded scope."""
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from packages.application.legacy_migration import (
    _finite,
    migration_scope,
    scope_query,
    verified_snapshot,
)
from packages.domain.annual_spread import annual_window_average
from packages.infrastructure.database_fields import PRICE_FIELDS


def reconcile_legacy_migration(manifest_path, target_path, node_id=None, market=None,
                               start_date=None, end_date=None):
    scope = migration_scope(node_id, market, start_date, end_date)
    manifest, source = verified_snapshot(manifest_path)
    target = Path(target_path).resolve()
    if not target.is_file():
        raise ValueError(f"迁移目标不存在：{target}")
    expected, raw = {}, {}
    source_where, params = scope_query(scope)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as src:
        src.row_factory = sqlite3.Row
        count = src.execute(f'SELECT COUNT(*) FROM price_data{source_where}', params).fetchone()[0]
        if count > 500000:
            raise ValueError('对账范围超过 500000 条，请按节点或日期分批')
        fields = ','.join(['id','node_id','run_date','case_type','publish_type','source_file',*PRICE_FIELDS])
        for row in src.execute(f'SELECT {fields} FROM price_data{source_where} ORDER BY id',params):
            values = [row[f] for f in PRICE_FIELDS]
            raw[row['id']] = dict(node_id=row['node_id'],run_date=row['run_date'],market=row['case_type'],publish_type=row['publish_type'],source_file=row['source_file'],prices=values)
            try:
                date.fromisoformat(row['run_date'])
            except (ValueError,TypeError):
                continue
            if row['case_type'] in {'日前','实时'} and all(_finite(v) for v in values):
                expected.setdefault((row['node_id'],row['run_date'],row['case_type']), [float(v) for v in values])
        names = {}
        if src.execute("SELECT 1 FROM sqlite_master WHERE name='nodes'").fetchone():
            names = {r[0]:(r[1],r[2] or '') for r in src.execute('SELECT id,node_name,province FROM nodes')}
    with closing(sqlite3.connect(target.as_uri()+'?mode=ro',uri=True)) as dst:
        dst.row_factory = sqlite3.Row
        meta = dict(dst.execute('SELECT key,value FROM staging_meta'))
        if meta.get('snapshot_sha256') != manifest['sha256']:
            raise ValueError('对账目标与快照来源不同')
        where, args = scope_query(scope,'market')
        actual = {(r['node_id'],r['run_date'],r['market']):json.loads(r['prices_json']) for r in dst.execute('SELECT * FROM canonical_price_curves'+where,args)}
        actual_raw = {r['source_row_id']:dict(node_id=r['node_id'],run_date=r['run_date'],market=r['market'],publish_type=r['publish_type'],source_file=r['source_file'],prices=json.loads(r['prices_json'])) for r in dst.execute('SELECT * FROM raw_price_records'+where,args)}
        target_names = {r[0]:(r[1],r[2] or '') for r in dst.execute('SELECT id,node_name,province FROM staging_nodes')}
        batches = dst.execute("SELECT COUNT(*) FROM migration_batches WHERE status='succeeded'").fetchone()[0]
        unfinished = dst.execute("SELECT COUNT(*) FROM migration_batches WHERE status='running'").fetchone()[0]
    missing = set(expected)-set(actual)
    unexpected = set(actual)-set(expected)
    changed = [k for k in expected.keys() & actual.keys() if expected[k] != actual[k]]
    raw_changed = [k for k in raw.keys() & actual_raw.keys() if json.dumps(raw[k],sort_keys=True) != json.dumps(actual_raw[k],sort_keys=True)]
    node_mismatches = [n for n in {r['node_id'] for r in raw.values()} if n in names and names[n] != target_names.get(n)]
    baseline = []
    for n,m in sorted({(r['node_id'],r['market']) for r in raw.values() if r['market'] in {'日前','实时'}}):
        left = [dict(run_date=r['run_date'],prices=r['prices']) for r in raw.values() if (r['node_id'],r['market'])==(n,m)]
        right = [dict(run_date=r['run_date'],prices=r['prices']) for r in actual_raw.values() if (r['node_id'],r['market'])==(n,m)]
        for hours in (2,4):
            def result(records, point_hours):
                try:
                    return annual_window_average(records, point_hours * 4)
                except ValueError as error:
                    return {'error':str(error)}
            a,b = result(left, hours),result(right, hours)
            baseline.append(dict(node_id=n,market=m,hours=hours,matched=a==b,
                                 comparison_scope='full_history' if not start_date and not end_date else 'date_sample',
                                 source=a,staging=b))
    matched = not (missing or unexpected or changed or raw_changed or set(raw)!=set(actual_raw) or node_mismatches or unfinished) and all(b['matched'] for b in baseline)
    return dict(status='matched' if matched else 'difference',scope=scope,
                source_complete_records=len(expected),canonical_records=len(actual),difference=len(actual)-len(expected),
                missing_keys=len(missing),unexpected_keys=len(unexpected),changed_curves=len(changed),
                raw_missing=len(set(raw)-set(actual_raw)),raw_unexpected=len(set(actual_raw)-set(raw)),raw_changed=len(raw_changed),
                node_mismatches=node_mismatches,source_first_date=min((k[1] for k in expected),default=None),
                source_last_date=max((k[1] for k in expected),default=None),
                canonical_first_date=min((k[1] for k in actual),default=None),canonical_last_date=max((k[1] for k in actual),default=None),
                succeeded_batches=batches,unfinished_batches=unfinished,snapshot_sha256=manifest['sha256'],baselines=baseline)
