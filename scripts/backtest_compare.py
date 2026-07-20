#!/usr/bin/env python
"""Backtest comparison driver.

Runs three strategy variants across multiple years and produces a
side-by-side comparison table.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN_RESEARCH = ROOT / 'run_research.py'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout,
)
log = logging.getLogger('backtest_compare')


@dataclass
class Strategy:
    name: str
    label: str
    args: list


STRATEGIES = {
    'A_5reversal': Strategy(
        name='A_5reversal',
        label='5-factor reversal (static)',
        args=['--factors-config', 'configs/factors_5reversal.yaml',
              '--strategy-mode', 'factor_dynamic'],
    ),
    'B_dynamic': Strategy(
        name='B_dynamic',
        label='Full pool + dynamic weights',
        args=['--factors-config', 'configs/factors_dynamic.yaml',
              '--strategy-mode', 'factor_dynamic'],
    ),
    'C_regime': Strategy(
        name='C_regime',
        label='Regime multi-sleeve',
        args=['--factors-config', 'configs/factors.yaml',
              '--strategy-mode', 'regime',
              '--regime-config', 'configs/regime.yaml'],
    ),
}


def _run_prefix(year, top_n):
    return f"{year}0101_{year}1231_top{top_n}_"


def _matching_runs(year, top_n):
    """Return run dirs matching this year/top-n prefix, newest first."""
    prefix = _run_prefix(year, top_n)
    runs_root = ROOT / 'outputs' / 'runs'
    if not runs_root.exists():
        return []
    return sorted(
        [pp for pp in runs_root.iterdir() if pp.is_dir() and pp.name.startswith(prefix)],
        key=lambda pp: pp.stat().st_mtime,
        reverse=True,
    )


def _find_existing_run(year, top_n):
    """Find most recent run dir for this year/top-n, if any."""
    candidates = _matching_runs(year, top_n)
    return candidates[0] if candidates else None


def _arg_value(args, flag):
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        return None
    return args[idx + 1]


def _manifest_matches_strategy(run_dir, strategy):
    manifest = run_dir / 'run_manifest.json'
    diag = run_dir / 'diagnostics' / 'phase2_period_return_diagnostics.json'
    if not manifest.exists() or not diag.exists():
        return False
    try:
        with open(manifest, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return False
    expected_mode = _arg_value(strategy.args, '--strategy-mode') or 'factor_dynamic'
    expected_factors = _arg_value(strategy.args, '--factors-config')
    expected_regime = _arg_value(strategy.args, '--regime-config')
    actual_mode = data.get('strategy_mode') or (data.get('extra') or {}).get('strategy_mode')
    actual_factors = data.get('factors_config') or (data.get('extra') or {}).get('factors_config')
    actual_regime = data.get('regime_config') or (data.get('extra') or {}).get('regime_config')
    if actual_mode != expected_mode or actual_factors != expected_factors:
        return False
    if expected_mode == 'regime' and actual_regime != expected_regime:
        return False
    return True


def _find_existing_strategy_run(year, top_n, strategy):
    for run_dir in _matching_runs(year, top_n):
        if _manifest_matches_strategy(run_dir, strategy):
            return run_dir
    return None


def run_one(year, strategy, top_n):
    """Run run_research.py phase2 for one (year, strategy)."""
    existing = _find_existing_strategy_run(year, top_n, strategy)
    if existing is not None:
        log.info('Cache hit %s for %s; skip', existing.name, strategy.name)
        return existing
    before = {pp.name for pp in _matching_runs(year, top_n)}
    cmd = [
        sys.executable, str(RUN_RESEARCH), 'phase2',
        '--start', str(year) + '0101',
        '--end', str(year) + '1231',
        '--top-n', str(top_n),
        '--no-recompute',
        *strategy.args,
    ]
    log.info('Running: ' + ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=False)
    stderr = proc.stderr.decode('utf-8', errors='replace') if proc.stderr else ''
    if proc.returncode != 0:
        log.error('Run failed rc=%d', proc.returncode)
        log.error('stderr tail: \n%s', stderr[-2000:])
        return None
    after = _matching_runs(year, top_n)
    new_runs = [pp for pp in after if pp.name not in before]
    if new_runs:
        return new_runs[0]
    return after[0] if after else None


METRIC_KEYS = [
    'n_periods', 'n_weekly_samples',
    'annualized_return', 'annualized_excess_return',
    'sharpe_ratio', 'information_ratio', 'max_drawdown',
    'period_return_std',
    'avg_regime_probs', 'avg_sleeve_weights',
    'regime_probs_dates', 'sleeve_weights_dates',
    'go_nogo_overall',
]


def extract_metrics(run_dir):
    if run_dir is None:
        return {'error': 'run failed'}
    diag_path = run_dir / 'diagnostics' / 'phase2_period_return_diagnostics.json'
    if not diag_path.exists():
        return {'error': 'diagnostics missing'}
    with open(diag_path, encoding='utf-8') as f:
        diag = json.load(f)
    out = {}
    for k in METRIC_KEYS:
        v = diag.get(k)
        if isinstance(v, dict):
            out[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
        else:
            out[k] = v
    pv = run_dir / 'diagnostics' / 'phase2_portfolio_values.csv'
    if pv.exists():
        df = pd.read_csv(pv)
        if 'period_return' in df.columns and len(df) > 0:
            rets = df['period_return'].astype(float)
            out['cum_return'] = float((1.0 + rets).prod() - 1.0)
            out['avg_period_return'] = float(rets.mean())
            out['win_rate'] = float((rets > 0).mean())
            if 'turnover' in df.columns:
                out['avg_turnover'] = float(df['turnover'].astype(float).mean())
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--years', nargs='+', type=int,
                   default=[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025])
    p.add_argument('--strategies', nargs='+', default=list(STRATEGIES.keys()))
    p.add_argument('--top-n', type=int, default=50)
    p.add_argument('--tag', default='default')
    args = p.parse_args()

    out_root = ROOT / 'outputs' / 'comparison' / args.tag
    out_root.mkdir(parents=True, exist_ok=True)

    rows = []
    existing_path = out_root / 'runs_partial.csv'
    if not existing_path.exists():
        existing_path = out_root / 'runs.csv'
    if existing_path.exists():
        try:
            rows = pd.read_csv(existing_path).to_dict('records')
            log.info('Loaded existing comparison rows: %s (%d rows)', existing_path, len(rows))
        except Exception as e:
            log.warning('Failed to load existing rows from %s: %s', existing_path, e)
            rows = []
    seen = {(int(r['year']), r['strategy']) for r in rows if 'year' in r and 'strategy' in r}
    for year in args.years:
        for strat_name in args.strategies:
            if (year, strat_name) in seen:
                log.info('Existing row %s/%s; skip', year, strat_name)
                continue
            strat = STRATEGIES[strat_name]
            run_dir = run_one(year, strat, args.top_n)
            metrics = extract_metrics(run_dir)
            row = {
                'year': year,
                'strategy': strat_name,
                'label': strat.label,
                **{k: metrics.get(k) for k in METRIC_KEYS},
                'cum_return': metrics.get('cum_return'),
                'avg_period_return': metrics.get('avg_period_return'),
                'win_rate': metrics.get('win_rate'),
                'avg_turnover': metrics.get('avg_turnover'),
                'run_dir': str(run_dir.relative_to(ROOT)) if run_dir else None,
            }
            rows.append(row)
            seen.add((year, strat_name))
            pd.DataFrame(rows).to_csv(
                out_root / 'runs_partial.csv',
                index=False,
                encoding='utf-8-sig',
            )

    df = pd.DataFrame(rows)
    csv_path = out_root / 'runs.csv'
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    log.info('Wrote %s (%d rows)', csv_path, len(df))

    md_path = out_root / 'summary.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('# Backtest comparison - tag=' + args.tag + chr(10) + chr(10))
        f.write('Years: ' + str(args.years) + chr(10) + chr(10))
        f.write('Strategies: ' + str(args.strategies) + chr(10) + chr(10))
        cols = ['year', 'strategy', 'cum_return', 'annualized_return',
                'annualized_excess_return', 'sharpe_ratio',
                'information_ratio', 'max_drawdown', 'avg_turnover', 'win_rate']
        sub = df[[c for c in cols if c in df.columns]].copy()
        for c in sub.select_dtypes(include='float').columns:
            sub[c] = sub[c].map(lambda v: '{:.4f}'.format(v) if pd.notnull(v) else '')
        f.write(sub.to_markdown(index=False))
        f.write(chr(10) + chr(10) + '## Regime diagnostics (strategy C)' + chr(10) + chr(10))
        c_only = df[df['strategy'] == 'C_regime']
        if not c_only.empty:
            f.write(c_only[['year', 'avg_regime_probs', 'avg_sleeve_weights',
                            'regime_probs_dates', 'sleeve_weights_dates']]
                    .to_markdown(index=False))
    log.info('Wrote %s', md_path)


if __name__ == '__main__':
    main()
