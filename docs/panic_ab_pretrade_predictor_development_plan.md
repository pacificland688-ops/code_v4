# Panic A/B Pre-trade Predictor Development Plan v2

## Overview

Phase 2: upgrade oracle A/B labels (Phase 1) to ex-ante predictor using t0-observable features.

## Default Configuration

| Parameter | v2 Default |
|-----------|-----------|
| Factor | `panic_drop_rev5_t05_bin_weekly_cs` |
| Direction | `drop` (long only) |
| Oracle retention threshold | `0.3` |
| Feature set | `price_only` (15 price features) |
| Model | `sklearn LogisticRegression(class_weight='balanced')` |
| Leakage control | `label_available_plus_embargo` |
| Embargo days | `20` trading days |
| Primary strategy | `date_rank_top_10pct` |
| Control strategies | `train_cutoff_top_*pct`, `fixed_0.*`, `baseline_rule`, `raw_events` |
| Output dir | `outputs/analysis/panic_reversal_gate/ab_pretrade_v2/` |

## Leakage Controls

1. **Label availability**: training excludes samples where `label_available_date >= test_start_trade_date`
2. **Embargo**: last training date is at least 20 trading days before first test date
3. **Feature ban**: all future-return and path columns excluded from features

## Output Files

```
ab_pretrade_v2/
  panic_ab_pretrade_v2_samples.parquet
  panic_ab_pretrade_v2_walkforward.csv
  panic_ab_pretrade_v2_strategy_compare.csv
  panic_ab_pretrade_v2_feature_importance.csv
  panic_ab_pretrade_v2_baseline.csv
  panic_ab_pretrade_v2_leakage_audit.csv
  panic_ab_pretrade_v2_report.md
  panic_ab_pretrade_v2_manifest.json
```

## Acceptance Criteria (date_rank_top_10pct)

- avg AUC > 0.52
- avg A-rate lift >= 3 pct
- avg net spread lift > 0
- >= 3 valid windows net spread lift > 0
- min window coverage >= 5%
- baseline_rule not significantly better than primary

## Run

```bash
python -u scripts/predict_panic_ab_pretrade.py \
  --start 20170101 --end 20251231 \
  --out-dir outputs/analysis/panic_reversal_gate/ab_pretrade_v2 \
  --retention-threshold 0.3 \
  --leakage-control label_available_plus_embargo \
  --embargo-days 20

pytest tests/test_panic_ab_pretrade_predictor.py -q
```
