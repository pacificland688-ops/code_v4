"""
Regression tests for standalone backtest phases.

Phase entry points must not rely on Phase 0 having populated global
singletons in the same process. They should explicitly load universe and
tradable dependencies before constructing PortfolioBacktester.
"""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_build_backtester_loads_universe_and_tradable():
    import run_research

    source = inspect.getsource(run_research._build_backtester)

    assert "get_universe_builder()" in source
    assert "universe.load(" in source
    assert "get_tradable()" in source
    assert "tradable.load(" in source
    assert "PortfolioBacktester(" in source


def test_backtest_phases_use_loaded_backtester_helper():
    import run_research

    for phase_fn in (
        run_research.run_phase2,
        run_research.run_phase3,
        run_research.run_phase5,
    ):
        source = inspect.getsource(phase_fn)

        assert "_build_backtester(" in source
        assert "PortfolioBacktester()" not in source
