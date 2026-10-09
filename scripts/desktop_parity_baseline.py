"""Read-only comparison against actual frozen 1.6.6 algorithms (not self-comparison).

Run with python -m scripts.desktop_parity_baseline --help. Outputs are evidence,
not approval for production. A difference exits 1; an incomplete run exits 2.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sqlite3
import subprocess
import sys
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from packages.domain.annual_spread import ALGORITHM_VERSION, annual_window_average
from packages.domain.financial_model import FinancialParameters, calculate_financials
from packages.domain.storage_dispatch import BatteryParameters, solve_day, validate_trajectory
from packages.infrastructure.database_fields import PRICE_FIELDS
from packages.infrastructure.staging_sqlite import StagingSQLiteReader


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
                          encoding='utf-8')


def compare(expected, actual, tolerance=1e-8, path='$'):
    """Full recursive comparison: missing fields, shape and nonfinite values fail."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return [diff for key in sorted(expected.keys() | actual.keys())
                for diff in compare(expected.get(key), actual.get(key), tolerance, path+'.'+key)]
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [{'field': path, 'expected_length': len(expected), 'actual_length': len(actual)}]
        return [diff for i, (left, right) in enumerate(zip(expected, actual))
                for diff in compare(left, right, tolerance, f'{path}[{i}]')]
    numeric = all(isinstance(x, (float, int)) and not isinstance(x, bool)
                  for x in (expected, actual))
    equal = (math.isfinite(expected) and math.isfinite(actual)
             and abs(expected-actual) <= tolerance) if numeric else expected == actual
    return [] if equal else [{'field': path, 'expected': expected, 'actual': actual}]


def fixtures():
    def curve(day, high=600):
        return {'run_date': str(day), 'prices': [-30.0]*32 + [float(high)]*32 + [120.0]*32}
    year = [curve(date(2024, 1, 1)+timedelta(days=i), 400+i % 73) for i in range(366)]
    return {
        'leap_complete_year': year + [curve('2025-02-01', 2000)],
        'incomplete_year': year[:60],
        'missing_day': year[:100] + year[101:],
        'duplicate_and_conflict': [curve('2025-01-01')]*5 + [curve('2025-01-01', 900),
                                   curve('2025-01-02', 300)],
        'incomplete_curve': [curve('2025-01-01'), {'run_date': '2025-01-02', 'prices': [None]*96}],
        'disjoint_extremes': [{'run_date': '2025-01-01', 'prices': [-100, 1000]*48}],
        'empty': [],
    }


def annual_case(records, hours, desktop):
    old = desktop.annual_window_average(records, (hours*4,))
    try:
        new = annual_window_average(records, hours*4)
    except ValueError:
        if old['valid_days'] == 0:
            return {'valid_days': 0}, {'valid_days': 0}
        raise
    expected = {key: old[key] for key in ('valid_days', 'available_days', 'excluded_records',
                                         'multiple_source_days', 'baseline_policy')}
    expected.update(start_date=old['period_start'], end_date=old['period_end'],
                    charge_price_yuan_per_mwh=old['stats'][hours*4]['low'],
                    discharge_price_yuan_per_mwh=old['stats'][hours*4]['high'],
                    spread_yuan_per_mwh=old['stats'][hours*4]['spread'])
    return expected, {key: new[key] for key in expected}


def add_case(report, folder, case_id, inputs, expected, actual, tolerance=1e-8):
    payload = {'inputs': inputs, 'desktop': expected, 'web': actual}
    path = folder / (case_id+'.json')
    save(path, payload)
    differences = compare(expected, actual, tolerance)
    report['cases'].append({'case_id': case_id, 'status': 'difference' if differences else 'passed',
                            'tolerance_absolute': tolerance, 'evidence': path.name,
                            'sha256': digest(path), 'differences': differences})


def freeze_desktop(release, output):
    manifest = json.loads((release/'release-manifest.json').read_text(encoding='utf-8-sig'))
    archive = release/'Banboos_V1.6.6_source-freeze.zip'
    entry = next(f for f in manifest['files'] if f['path'] == archive.name)
    if digest(archive) != entry['sha256'].lower():
        raise ValueError('冻结桌面源码哈希与发布清单不一致')
    package = output/'desktop'/'analysis'
    package.mkdir(parents=True)
    (package/'__init__.py').write_text('', encoding='utf-8')
    hashes = {}
    # Copy only known algorithm files. Never extract arbitrary archive paths.
    with ZipFile(archive) as bundle:
        for name in ('annual_spread', 'window_mean', 'lp_optimizer', 'strict_dispatch', 'legacy_finance'):
            path = package/(name+'.py')
            path.write_bytes(bundle.read('analysis/'+name+'.py'))
            hashes[name] = digest(path)
    if 'analysis' in sys.modules:
        raise RuntimeError('需在独立 Python 进程运行，避免桌面模块缓存污染')
    sys.path.insert(0, str(package.parent))
    return {'archive': str(archive), 'archive_sha256': digest(archive), 'module_hashes': hashes}


def run(args, folder, report):
    report['desktop_source'] = freeze_desktop(args.release.resolve(), folder)
    annual = importlib.import_module('analysis.annual_spread')
    lp = importlib.import_module('analysis.lp_optimizer')
    finance = importlib.import_module('analysis.legacy_finance')
    report['annual_algorithm_version'] = ALGORITHM_VERSION
    report['desktop_annual_algorithm_version'] = annual.METHOD_ID
    for name, rows in fixtures().items():
        for hours in (2, 4):
            left, right = annual_case(rows, hours, annual)
            add_case(report, folder, f'fixture-{name}-{hours}h', rows, left, right)

    manifest = json.loads(args.snapshot.read_text(encoding='utf-8-sig'))
    source = args.snapshot.parent / Path(manifest['snapshot_path']).name
    if digest(source) != manifest['sha256']:
        raise ValueError('隔离源库哈希不一致')
    staging_hash = digest(args.staging)
    reader = StagingSQLiteReader(args.staging)
    if reader.metadata['snapshot_sha256'] != manifest['sha256']:
        raise ValueError('staging 与源库不是同一快照')
    report['data'] = {'snapshot_sha256': manifest['sha256'], 'staging_sha256': staging_hash,
                      'snapshot': str(source.resolve()), 'staging': str(args.staging.resolve())}
    report['sample_nodes'] = args.nodes
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        for node in args.nodes:
            for market in ('日前', '实时'):
                rows = [dict(run_date=r['run_date'], prices=[r[f] for f in PRICE_FIELDS])
                        for r in db.execute('SELECT run_date,'+','.join(PRICE_FIELDS)+
                            ' FROM price_data WHERE node_id=? AND case_type=? ORDER BY run_date,id',
                            (node, market))]
                migrated = reader.baseline_curves(node, market)
                if not rows or not migrated:
                    raise ValueError(f'{node}/{market} 无记录，不能计为通过')
                add_case(report, folder, f'raw-{node}-{market}', {'node': node, 'market': market},
                         rows, migrated, 0)
                for hours in (2, 4):
                    left, _ = annual_case(rows, hours, annual)
                    _, right = annual_case(migrated, hours, annual)
                    add_case(report, folder, f'annual-{node}-{market}-{hours}h', rows, left, right)
                valid = [r for r in rows if len(r['prices']) == 96 and
                         all(v is not None and math.isfinite(v) for v in r['prices'])]
                if not valid:
                    raise ValueError('无完整曲线用于独立 LP 验证')
                sample = valid[len(valid)//2]
                for hours in (2, 4):
                    p = BatteryParameters(power_mw=120/hours, capacity_mwh=120)
                    old = lp.LPOptimizer(lp.BatteryParams(power_rated=p.power_mw,
                                                          capacity=p.capacity_mwh)).solve_day(
                                                              sample['prices'], sample['run_date'])
                    if not old.success:
                        raise ValueError('桌面 LP 求解失败：'+old.message)
                    new = solve_day(sample['prices'], p)
                    validate_trajectory(old.p_ch, old.p_dis, old.soc, p)
                    validate_trajectory(new.charge_mw, new.discharge_mw, new.soc, p)
                    expected = {'net_revenue_yuan': old.revenue_net, 'charge_energy_mwh': old.energy_ch,
                                'discharge_energy_mwh': old.energy_dis, 'cycles': old.cycles,
                                'shutdown': old.shutdown}
                    actual = {key: asdict(new)[key] for key in expected}
                    # Multiple optimal trajectories are allowed; persist both, audit feasibility.
                    add_case(report, folder, f'lp-{node}-{market}-{hours}h',
                             {'curve': sample, 'parameters': asdict(p),
                              'desktop_trajectory': [old.p_ch, old.p_dis, old.soc],
                              'web_trajectory': [new.charge_mw, new.discharge_mw, new.soc]},
                             expected, actual, 0.01)

    # Explicit unit-normalized mapping, not inferred equivalence of differing defaults.
    for hours in (2, 4):
        for loan in (0.0, 0.7):
            revenue = (520*.92-50/.92)*120*.95*350
            p = FinancialParameters(power_mw=120/hours, capacity_mwh=120,
                                    annual_revenue_yuan=revenue, loan_ratio=loan,
                                    discount_rate=.04, eol_method='desktop_template',
                                    calendar_eol_decline=.005, insurance_rate=.002,
                                    fixed_operation_cost_yuan=2_000_000,
                                    replace_year=11, replace_capex_yuan=36_000_000,
                                    vat_rate=.13, equipment_investment_share=0.0)
            old_p = dict(finance.DEFAULT_BASIC_PARAMS, system_power_mw=p.power_mw,
                         battery_capacity_mwh=120, loan_ratio=loan, charge_price=.05,
                         discharge_price=.52, operator_share_ratio=0)
            investment = {'dynamic_total_wan': (p.initial_investment_yuan +
                          p.initial_investment_yuan*loan*.045*.5)/10000,
                          'epc_total_wan': p.initial_investment_yuan/10000, 'rows': []}
            old = finance.calculate_financial_metrics(old_p, investment)
            new = calculate_financials(p)
            expected = {'cashflows_yuan': [v*10000 for v in old['full_cashflows']],
                        'equity_cashflows_yuan': [v*10000 for v in old['equity_cashflows']],
                        'full_npv_yuan': old['summary']['full_npv_wan']*10000,
                        'first_year_revenue_yuan': old['yearly_rows'][0]['revenue_wan']*10000}
            actual = {key: new[key] for key in expected if key in new}
            actual['first_year_revenue_yuan'] = new['yearly'][0]['revenue_yuan']
            add_case(report, folder, f'finance-{hours}h-loan{loan}',
                     {'desktop': old_p, 'investment': investment, 'web': asdict(p),
                      'mapping_scope': 'explicit_inputs_known_rule_differences_not_full_UI_mapping'},
                     expected, actual, .01)
    report['data']['unchanged'] = (digest(source) == manifest['sha256'] and
                                   digest(args.staging) == staging_hash)
    if not report['data']['unchanged']:
        raise ValueError('运行期间输入数据库变化，证据不可发布')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--staging', type=Path, required=True)
    parser.add_argument('--nodes', type=int, nargs='+', required=True)
    parser.add_argument('--output-root', type=Path, default=Path('var/parity'))
    args = parser.parse_args()
    run_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    folder = args.output_root.resolve()/run_id
    folder.mkdir(parents=True, exist_ok=False)
    report = {'run_id': run_id, 'purpose': 'independent_desktop_comparison', 'cases': [],
              'scope': 'sampled annual/strict LP/mapped financial model; not full UI or XLSM parity',
              'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'worktree_status': subprocess.check_output(['git', 'status', '--short'], text=True),
              'runner_sha256': digest(__file__)}
    try:
        run(args, folder, report)
        report['status'] = 'differences' if any(c['status'] != 'passed' for c in report['cases']) else 'passed'
    except Exception as error:  # noqa: BLE001 - persist any failed run as audit evidence
        report.update(status='incomplete', error=f'{type(error).__name__}: {error}')
    report['counts'] = dict(Counter(c['status'] for c in report['cases']))
    save(folder/'report.json', report)
    print(json.dumps({'report': str(folder/'report.json'), 'status': report['status'],
                      'counts': report['counts'], 'error': report.get('error')}, ensure_ascii=False))
    return {'passed': 0, 'differences': 1, 'incomplete': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
