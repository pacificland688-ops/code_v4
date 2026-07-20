# Strategy Family GO / NO-GO Decision

生成日期：2026-06-14 08:54

## Investment Status

| Strategy | Investment Status | Avg Excess | Excess Reliable | Pos Years | Avg IR | Max Loss |
|---|---:|---:|---:|---:|---:|
| A_5reversal | 🔴 **NO_GO** | -11.7% | ✅ | 2/8 | -0.81 | -26.9% |
| B_dynamic | 🔴 **NO_GO** | -12.1% | ✅ | 1/8 | -1.10 | -25.5% |
| C_regime_baseline | 🔴 **NO_GO** | -9.5% | ✅ | 1/8 | -0.70 | -25.0% |
| D_regime_overlay | 🔴 **NO_GO** | -7.9% | ✅ | 2/8 | -0.64 | -24.7% |
| E_shock_reversal | 🔴 **NO_GO** | -10.2% | ✅ | 2/8 | -0.72 | -28.9% |

## Recommendations

### 🔴 NO-GO
- **A_5reversal**: avg_return=-9.6% <= 0.0%; avg_excess=-11.7% < 2.0%; median_excess=-12.1% <= 0.0%; pos_years=2/8 < 5/8; avg_ir=-0.81 < 0.30; max_loss=-26.9% < -10.0%
- **B_dynamic**: avg_return=-9.9% <= 0.0%; avg_excess=-12.1% < 2.0%; median_excess=-10.0% <= 0.0%; pos_years=1/8 < 5/8; avg_ir=-1.10 < 0.30; max_loss=-25.5% < -10.0%
- **C_regime_baseline**: avg_return=-7.3% <= 0.0%; avg_excess=-9.5% < 2.0%; median_excess=-10.0% <= 0.0%; pos_years=1/8 < 5/8; avg_ir=-0.70 < 0.30; max_loss=-25.0% < -10.0%
- **D_regime_overlay**: avg_return=-5.7% <= 0.0%; avg_excess=-7.9% < 2.0%; median_excess=-10.2% <= 0.0%; pos_years=2/8 < 5/8; avg_ir=-0.64 < 0.30; max_loss=-24.7% < -10.0%
- **E_shock_reversal**: avg_return=-8.1% <= 0.0%; avg_excess=-10.2% < 2.0%; median_excess=-10.0% <= 0.0%; pos_years=2/8 < 5/8; avg_ir=-0.72 < 0.30; max_loss=-28.9% < -10.0%

## Path Forward

**All strategies are NO-GO for production.**

Recommended actions:
1. Review factor scorecard — which factors survive the strict retention gate?
2. If 0 factors survive → **Kill / Restart**: current factor pool cannot support positive alpha.
3. If 1-3 factors survive → **Alpha salvage**: build minimal candidate pool from surviving factors.
4. If gross excess positive but net negative → **Construction repair**: fix costs and constraints.
5. Do NOT continue tuning regime weights — the alpha layer must be fixed first.

