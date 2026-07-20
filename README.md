# code_v4: CSI 300 Cross-Sectional Multi-Factor Strategy

## Quick Start

```bash
# 1. Check your environment
python scripts/check_env.py

# 2. Smoke test (1 month, real data, ~30 seconds)
python run_research.py smoke --start 20160101 --end 20160229

# 3. Dry-run verification (no data fetch)
python run_research.py phase0 --dry-run
python run_research.py phase3 --dry-run
```

## Runtime Boundaries

### Memory Requirements

| Available RAM | Recommendation |
|--------------|----------------|
| < 1GB | **FAIL** — cannot run live data processing. Dry-run only. |
| 1-4GB | **WARN** — dry-run OK, short smoke test OK. Avoid 10yr full runs. |
| 4-8GB | **OK** — can run 1-year intervals safely. |
| > 8GB | Full 10-year CSI 300 processing supported. |

Override thresholds with env vars:
```bash
set CODE_V4_MEMORY_WARN_GB=3.0    # WARN below 3GB
set CODE_V4_MEMORY_FAIL_GB=0.5    # FAIL below 0.5GB
```

### Incremental Approach

For full backtest runs (2016–present), follow this sequence:

```bash
# Step 1: Verify environment and one month
python scripts/check_env.py
python run_research.py smoke --start 20160101 --end 20160229

# Step 2: Run one year
python run_research.py phase0 --start 20160101 --end 20161231
python run_research.py phase1 --start 20160101 --end 20161231

# Step 3: Run full range
python run_research.py all --start 20160101
```

Close other memory-intensive applications before running Phase 0 on the full range.

## Phase Reference

| Phase | Command | Description |
|-------|---------|-------------|
| 0 | `python run_research.py phase0 --start YYYYMMDD --end YYYYMMDD` | Data pipeline: fetch raw, compute adj, build universe |
| 1 | `python run_research.py phase1` | Factor computation + cross-sectional evaluation |
| 2 | `python run_research.py phase2 --top-n 50` | MVP equal-weight backtest |
| 3 | `python run_research.py phase3` | Mean-variance optimization (requires cvxpy) |
| 4 | `python run_research.py phase4` | ML alpha (walk-forward GBDT) |
| 5 | `python run_research.py phase5` | Robustness tests + Go/No-Go |
| smoke | `python run_research.py smoke --start YYYYMMDD --end YYYYMMDD` | Short-interval E2E validation |
| all | `python run_research.py all` | Run Phase 0→5 sequentially |

All phases support `--dry-run` for import/module verification without data fetching.

## Memory Architecture

Phase 0 processes data in **quarterly close-loop chunks**:
1. Fetch raw prices for one quarter
2. Fetch adj_factors for that quarter's stocks only (batched at 100 stocks/call)
3. Compute adjusted prices
4. Write partitioned parquet
5. Release memory (`del` + `gc.collect()`)

No full-range DataFrames are ever accumulated. Peak memory stays < 2GB even for 10-year CSI 300 processing.

## Key Constraints

- **Price limits:** Backtester checks limit-up/down at open via `TradableMask` with auto-fetched `stk_limit` data
- **PIT universe:** `index_weight` snapshots apply availability lag (default 1 trade day) — month-end snapshot not usable on its own date
- **weight_max:** Threaded through full call chain; infeasible configs (top_n × weight_max < 1.0) detected and reported
- **Industry deviation:** Only enabled when PIT industry data with effective dates is available (static stock_basic industry data is NOT sufficient)

## Environment

Requires `TUSHARE_TOKEN` in `.env` for live data fetching. Dry-run and cached reads work without it.

```bash
cp .env.example .env
# Edit .env and set your Tushare Pro token
```
