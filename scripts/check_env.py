#!/usr/bin/env python
"""
Environment check script for code_v4.

Verifies:
- Python version >= 3.10
- Core dependencies (pandas, numpy, scipy, pyarrow)
- cvxpy and solver availability for Phase 3+
- Tushare token configuration
- Memory budget awareness

Three-tier output: OK / WARN / FAIL
- FAIL: blocks operation, exit code 1
- WARN: degraded but functional, exit code 0
- OK: nominal

Env var overrides:
- CODE_V4_MEMORY_WARN_GB: memory threshold for WARN (default 4.0)
- CODE_V4_MEMORY_FAIL_GB: memory threshold for FAIL (default 1.0)

Usage:
    python scripts/check_env.py
    python scripts/check_env.py --full  # includes Tushare connectivity check
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Check result builder
# ---------------------------------------------------------------------------
def result(name: str, value: str, level: str = "OK", detail: str = "") -> dict:
    """Build a check result dict."""
    return {"name": name, "value": value, "level": level, "detail": detail}


def _mem_threshold(env_var: str, default_gb: float) -> float:
    """Read memory threshold from env var, fall back to default."""
    val = os.getenv(env_var)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return default_gb


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def check_python_version() -> dict:
    vi = sys.version_info
    if vi >= (3, 10):
        return result("Python version", f"{vi.major}.{vi.minor}.{vi.micro}")
    else:
        return result("Python version", f"{vi.major}.{vi.minor}.{vi.micro}",
                      "FAIL", "Requires >=3.10")


def check_core_dep(module_name: str, required: bool = True,
                   attr: str = "__version__") -> dict:
    """Check a Python dependency.

    required=True  -> FAIL on missing
    required=False -> WARN on missing (optional accelerator)
    """
    try:
        mod = __import__(module_name)
        version = getattr(mod, attr, "?")
        if callable(version):
            version = "available"
        return result(module_name, str(version))
    except ImportError:
        level = "FAIL" if required else "WARN"
        msg = f"{module_name} not installed"
        if not required:
            msg += " (optional — falling back to PyArrow scans)"
        else:
            msg += f". Install with: pip install {module_name}"
        return result(module_name, "MISSING", level, msg)


def check_cvxpy_solvers() -> dict:
    try:
        import cvxpy
        solvers = cvxpy.installed_solvers()
        preferred = ["ECOS", "OSQP", "SCS", "CLARABEL"]
        available = [s for s in preferred if s in solvers]
        if available:
            return result("cvxpy solvers",
                          f"cvxpy {cvxpy.__version__}, solvers: {available}")
        else:
            return result("cvxpy solvers",
                          f"cvxpy {cvxpy.__version__}, no preferred solver",
                          "FAIL",
                          "No ECOS/OSQP/SCS solver. Install: pip install ecos")
    except ImportError:
        return result("cvxpy solvers", "MISSING", "FAIL",
                      "cvxpy not installed. Phase 3+ requires: pip install cvxpy>=1.4.0")


def check_tushare_token() -> dict:
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("TUSHARE_TOKEN", "")
    has_token = bool(token and token != "your_tushare_pro_token_here")
    if has_token:
        return result("Tushare token", "configured")
    else:
        return result("Tushare token", "NOT SET", "WARN",
                      "Set TUSHARE_TOKEN in .env for live data fetching "
                      "(dry-run / cached-read works without it)")


def check_tushare_connectivity() -> dict:
    try:
        from data.tushare_client import get_client
        client = get_client()
        if client.available:
            cal = client.get_trade_cal(exchange="SSE",
                                       start_date="20240101", end_date="20240131")
            if not cal.empty:
                return result("Tushare connectivity", f"OK ({len(cal)} trade days)")
        return result("Tushare connectivity", "UNAVAILABLE", "FAIL",
                      "Tushare Pro API not reachable. Check token and network.")
    except Exception as e:
        return result("Tushare connectivity", "ERROR", "FAIL", str(e))


def check_memory_budget() -> dict:
    warn_gb = _mem_threshold("CODE_V4_MEMORY_WARN_GB", 4.0)
    fail_gb = _mem_threshold("CODE_V4_MEMORY_FAIL_GB", 1.0)
    try:
        import psutil
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        value = f"{available_gb:.1f}GB available / {total_gb:.1f}GB total"

        if available_gb < fail_gb:
            return result("System memory", value, "FAIL",
                          f"Available memory {available_gb:.1f}GB < {fail_gb}GB threshold "
                          f"(set CODE_V4_MEMORY_FAIL_GB to adjust)")
        elif available_gb < warn_gb:
            return result("System memory", value, "WARN",
                          f"Available memory {available_gb:.1f}GB < {warn_gb}GB threshold "
                          f"(set CODE_V4_MEMORY_WARN_GB to adjust)")
        else:
            return result("System memory", value)
    except ImportError:
        return result("System memory", "unknown (psutil not installed)", "WARN",
                      "Install psutil for memory monitoring: pip install psutil")


def check_parquet_cache() -> dict:
    cache_path = Path("data/parquet")
    if cache_path.exists():
        n_files = len(list(cache_path.rglob("*.parquet")))
        total_size = sum(f.stat().st_size for f in cache_path.rglob("*.parquet"))
        size_mb = total_size / (1024 * 1024)
        detail = "Cache empty — data will be fetched on first run" if n_files == 0 else ""
        return result("Parquet cache", f"{n_files} files, {size_mb:.0f}MB", "OK", detail)
    else:
        return result("Parquet cache", "not created yet", "OK",
                      "Will be created on first data fetch")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="code_v4 environment check")
    parser.add_argument("--full", action="store_true",
                        help="Include Tushare connectivity test")
    args = parser.parse_args()

    print("=" * 60)
    print("code_v4 Environment Check")
    print("=" * 60)

    checks = [
        check_python_version(),
        check_core_dep("numpy", required=True),
        check_core_dep("pandas", required=True),
        check_core_dep("scipy", required=True),
        check_core_dep("pyarrow", required=True),
        check_core_dep("duckdb", required=False),   # optional accelerator
        check_cvxpy_solvers(),
        check_tushare_token(),
        check_memory_budget(),
        check_parquet_cache(),
    ]

    if args.full:
        checks.append(check_tushare_connectivity())

    # Print results with tier badges
    has_fail = False
    has_warn = False
    for check in checks:
        level = check["level"]
        badge = {"OK": "[OK]  ", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(level, "[???] ")
        print(f"\n  {badge} {check['name']}: {check['value']}")
        if check["detail"]:
            print(f"         {check['detail']}")
        if level == "FAIL":
            has_fail = True
        elif level == "WARN":
            has_warn = True

    # Summary
    print("\n" + "=" * 60)
    if has_fail:
        print("Verdict: FAIL — review failures above and re-run")
        print("Some checks failed — these will block operation.")
        return 1
    elif has_warn:
        print("Verdict: WARN — functional with caveats (see above)")
        print("Warnings are non-blocking; dry-run and cached reads still work.")
    else:
        print("Verdict: OK — all checks passed")

    # Runtime guidance based on memory
    print("\nRuntime guidance:")
    mem_check = [c for c in checks if c["name"] == "System memory"]
    if mem_check:
        mem_level = mem_check[0]["level"]
        if mem_level == "FAIL":
            print("  - Memory is critically low (< 1GB available).")
            print("  - SAFE: python run_research.py phase0 --dry-run")
            print("  - SAFE: python -m pytest -q")
            print("  - AVOID: live data fetch or full backtest runs.")
        elif mem_level == "WARN":
            print("  - Memory is below recommended threshold (< 4GB available).")
            print("  - SAFE: dry-run, pytest, cache audit")
            print("  - OPTIONAL: python run_research.py smoke --start 20160101 --end 20160229")
            print("  - RECOMMENDED: python run_research.py validate --start 20160101 --end 20161231")
            print("  - CAUTION: avoid 10yr full runs while available memory is below 4GB")
        else:
            print("  - Memory is sufficient.")
            print("  - You can run: python run_research.py validate --start 20160101 --end 20161231")
            print("  - Optional short smoke: python run_research.py smoke --start 20160101 --end 20160229")
            print("  - Full range: python run_research.py all --start 20160101")

    # Suggest next command
    print("\nSuggested next command:")
    if has_fail:
        print("  Fix FAIL items above, then re-run check_env.py")
    else:
        print("  python scripts/audit_cache.py --start 20160101 --end 20161231")
        print("  python run_research.py validate --start 20160101 --end 20161231")

    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())
