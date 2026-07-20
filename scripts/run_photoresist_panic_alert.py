"""Close-of-day photoresist panic alert (research-only, frozen primary_5d).

Usage:
    python scripts/run_photoresist_panic_alert.py --initialize-state   # first deploy
    python scripts/run_photoresist_panic_alert.py                      # daily run
    python scripts/run_photoresist_panic_alert.py --as-of 20260715 --no-refresh

First deployment MUST pick an explicit mode:
    --initialize-state  start from a proven-IDLE quiet-window checkpoint, or
                        replay all available history when no proof exists;
                        no historical notifications are sent
    --fresh-start       start from today; the manifest records that an
                        in-flight event may have been missed

Recommended schedule: trading days after 16:30. Exit codes:
    0 = status produced, 2 = BLOCKED by data quality gate,
    3 = runtime failure, 4 = first deploy requires an init mode.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):  # Windows GBK console safety
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Photoresist panic live alert (frozen primary_5d)"
    )
    parser.add_argument("--as-of", type=int,
                        default=int(date.today().strftime("%Y%m%d")))
    parser.add_argument("--live-config",
                        default=str(ROOT / "configs" / "photoresist_panic_live.yaml"))
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--no-refresh", action="store_true",
                        help="skip Tushare incremental update (local data only)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--initialize-state", action="store_true",
                      help="first deploy: use a proven-IDLE checkpoint or full "
                           "history; suppress historical notifications")
    mode.add_argument("--fresh-start", action="store_true",
                      help="first deploy: start from today; manifest flags a "
                           "possibly missed in-flight event")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from live.photoresist_panic.runner import run_daily

    init_mode = None
    if args.initialize_state:
        init_mode = "initialize_state"
    elif args.fresh_start:
        init_mode = "fresh_start"
    return run_daily(
        as_of=args.as_of,
        live_config_path=args.live_config,
        out_dir=args.out_dir,
        refresh_data=not args.no_refresh,
        init_mode=init_mode,
    )


if __name__ == "__main__":
    raise SystemExit(main())
