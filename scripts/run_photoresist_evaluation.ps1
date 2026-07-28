# ============================================================================
# Photoresist Panic — Full Evaluation Pipeline Runner
# ============================================================================
# Runs the complete pipeline:
#   1. Fetch data from Tushare
#   2. Build panic events (Phase 1-3)
#   3. Evaluate path rules R0-R3 (Phase 0)
#   4. Run unit tests
#
# Usage:
#   .\scripts\run_photoresist_evaluation.ps1
#   .\scripts\run_photoresist_evaluation.ps1 -SkipFetch   # skip data fetch
#   .\scripts\run_photoresist_evaluation.ps1 -SkipTests    # skip tests
# ============================================================================

param(
    [switch]$SkipFetch,
    [switch]$SkipTests,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Photoresist Panic — Full Evaluation Pipeline" -ForegroundColor Cyan
Write-Host "  Root: $RootDir" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# ── Find Python ──────────────────────────────────────────────────────────
$Python = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $v = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $Python = $candidate
            Write-Host "`nPython: $v" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $Python) {
    Write-Host "`nERROR: Python not found. Install Python 3.10+ first:" -ForegroundColor Red
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# ── Check Tushare token ─────────────────────────────────────────────────
if (-not $SkipFetch) {
    $envPath = Join-Path $RootDir ".env"
    if (-not (Test-Path $envPath)) {
        Write-Host "ERROR: .env file not found at $envPath" -ForegroundColor Red
        exit 1
    }
    $token = Select-String -Path $envPath -Pattern "TUSHARE_TOKEN=(.+)" | ForEach-Object { $_.Matches.Groups[1].Value }
    if (-not $token -or $token -eq "your_tushare_pro_token_here") {
        Write-Host "ERROR: Tushare token not configured in .env" -ForegroundColor Red
        Write-Host "  1. Edit .env in project root" -ForegroundColor Yellow
        Write-Host "  2. Set TUSHARE_TOKEN=your_actual_token" -ForegroundColor Yellow
        Write-Host "  3. Token at: https://tushare.pro/user/token" -ForegroundColor Yellow
        exit 1
    }
}

# ── Check dependencies ───────────────────────────────────────────────────
Write-Host "`n--- Checking dependencies ---" -ForegroundColor Cyan
& $Python -c "import tushare, pandas, numpy, pyarrow, yaml, dotenv, scipy; print('  All core deps OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Missing dependencies. Installing..." -ForegroundColor Yellow
    & $Python -m pip install tushare pandas numpy pyarrow pyyaml python-dotenv pytest scipy
}

# ── Check-only mode ──────────────────────────────────────────────────────
if ($CheckOnly) {
    Write-Host "`n--- Cache check ---" -ForegroundColor Cyan
    & $Python scripts/fetch_photoresist_data.py --check
    exit 0
}

# ── Step 1: Data fetch ──────────────────────────────────────────────────
if (-not $SkipFetch) {
    Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
    Write-Host "STEP 1/4: Fetching data from Tushare" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    & $Python scripts/fetch_photoresist_data.py --start 20150101 --end 20251231
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nData fetch failed. Check errors above and retry." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`n[SKIP] Data fetch" -ForegroundColor Yellow
}

# ── Step 2: Build panic events ───────────────────────────────────────────
Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "STEP 2/4: Building panic events (Phase 1-3)" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
& $Python scripts/build_photoresist_panic_events.py --start 20170101 --end 20251231
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nEvent build failed. Check errors above." -ForegroundColor Red
    exit 1
}

# ── Step 3: Evaluate path rules R0-R3 ────────────────────────────────────
Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "STEP 3/4: Evaluating path rules R0-R3 (Phase 0)" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
& $Python scripts/evaluate_photoresist_panic_path_rules.py --start 20170101 --end 20251231 --strict-tradability --volume-diagnostics
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nPath rule evaluation failed. Check errors above." -ForegroundColor Red
    exit 1
}

# ── Step 4: Unit tests ──────────────────────────────────────────────────
if (-not $SkipTests) {
    Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
    Write-Host "STEP 4/4: Running unit tests" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    $test_files = @(
        "tests/test_photoresist_panic_path_rules.py",
        "tests/test_volume_enhancement.py",
        "tests/test_cache_coverage.py"
    )
    $all_passed = $true
    foreach ($tf in $test_files) {
        if (Test-Path $tf) {
            Write-Host "`n--- $tf ---" -ForegroundColor Cyan
            & $Python -m pytest $tf -v --tb=short
            if ($LASTEXITCODE -ne 0) {
                Write-Host "FAILED: $tf" -ForegroundColor Red
                $all_passed = $false
            }
        }
    }
    if (-not $all_passed) {
        Write-Host "`nERROR: Some test suites failed. Review output above." -ForegroundColor Red
        exit 1
    }
}

# ── Done ─────────────────────────────────────────────────────────────────
Write-Host "`n" + ("=" * 60) -ForegroundColor Green
Write-Host "PIPELINE COMPLETE" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""
Write-Host "Output files:" -ForegroundColor White
Write-Host "  outputs/analysis/photoresist_panic/photoresist_core_basket_with_gate.csv"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_event_path_ledger.csv"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_rule_trade_ledger.csv"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_path_rules_report.md"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_volume_feature_ledger.csv"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_volume_validation_firewall.json"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_path_rules_manifest.json"
Write-Host "  outputs/analysis/photoresist_panic/photoresist_volume_feature_ledger.csv  (if --volume-diagnostics)"
Write-Host ""
Write-Host "Read the markdown report for acceptance evaluation results."
