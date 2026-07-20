from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from monitor_photoresist_panic import classify_severity, data_is_stale  # noqa: E402
from validate_photoresist_panic_thresholds import load_validation_inputs  # noqa: E402


SEVERITY = {
    "l2_absolute_return": -0.05, "l3_absolute_return": -0.08,
    "l4_absolute_return": -0.10, "l3_percentile": 0.05,
    "l4_percentile": 0.01, "l4_breadth": 0.75, "watch_percentile": 0.20,
}


def test_small_absolute_drop_can_be_relative_panic():
    assert classify_severity(True, -0.035, 0.04, 0.60, SEVERITY) == "PANIC_L3"


def test_absolute_panic_levels_are_ordered():
    assert classify_severity(True, -0.06, 0.08, 0.60, SEVERITY) == "PANIC_L2"
    assert classify_severity(True, -0.085, 0.08, 0.60, SEVERITY) == "PANIC_L3"
    assert classify_severity(True, -0.11, 0.08, 0.60, SEVERITY) == "PANIC_L4"


def test_non_trigger_is_watch_not_panic():
    assert classify_severity(False, -0.02, 0.15, 0.60, SEVERITY) == "WATCH"


def test_staleness_is_explicit():
    assert data_is_stale(20260605, 20260715, 3)
    assert not data_is_stale(20260714, 20260715, 3)


def test_frozen_input_contract_returns_universe_second():
    _, universe = load_validation_inputs(
        ROOT / "outputs" / "analysis" / "photoresist_panic_bbb_full"
    )
    assert "pool_type" in universe.columns


def test_repository_data_package_is_importable_from_monitor():
    from data.adjust import PriceAdjuster

    assert PriceAdjuster is not None
