"""
Test: generate_go_nogo_decision — completeness check, refusal on incomplete, --allow-incomplete.
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.generate_go_nogo_decision import (
    check_completeness,
    compute_summary,
    evaluate_thresholds,
    REQUIRED_VALIDATION_YEARS,
    REQUIRED_YTD_YEARS,
)


class TestCheckCompleteness:
    """Year coverage completeness checks."""

    def test_all_years_present(self):
        """Complete coverage → is_complete=True, no issues."""
        rows = []
        for year in REQUIRED_VALIDATION_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
            })
        for year in REQUIRED_YTD_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "ytd",
                "annualized_excess_return": 0.03,
            })
        df = pd.DataFrame(rows)
        result = check_completeness(df, ["E_candidate_v2"])
        assert result["is_complete"] is True
        assert len(result["issues"]) == 0

    def test_missing_validation_years(self):
        """Missing validation years → is_complete=False with details."""
        rows = []
        for year in [2023, 2024]:  # Only 2 of 8 validation years
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
            })
        df = pd.DataFrame(rows)
        result = check_completeness(df, ["E_candidate_v2"])
        assert result["is_complete"] is False
        assert len(result["issues"]) > 0
        assert "E_candidate_v2" in result["missing_validation"]
        missing = result["missing_validation"]["E_candidate_v2"]
        assert 2017 in missing
        assert 2018 in missing
        assert 2023 not in missing

    def test_missing_ytd_years(self):
        """Missing YTD → flagged in issues."""
        rows = []
        for year in REQUIRED_VALIDATION_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
            })
        # No YTD rows
        df = pd.DataFrame(rows)
        result = check_completeness(df, ["E_candidate_v2"])
        assert result["is_complete"] is False
        assert len(result["missing_ytd"].get("E_candidate_v2", [])) > 0

    def test_no_candidate_data_at_all(self):
        """No data for candidate → all years reported missing."""
        df = pd.DataFrame(columns=["strategy", "year", "sample", "annualized_excess_return"])
        result = check_completeness(df, ["E_candidate_v2"])
        assert result["is_complete"] is False
        assert len(result["missing_validation"]["E_candidate_v2"]) == len(REQUIRED_VALIDATION_YEARS)

    def test_multiple_candidates_checked_independently(self):
        """Each candidate is checked independently."""
        rows = []
        for year in REQUIRED_VALIDATION_YEARS:
            rows.append({
                "strategy": "candidate_a",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
            })
        df = pd.DataFrame(rows)
        result = check_completeness(df, ["candidate_a", "candidate_b"])
        assert result["is_complete"] is False  # candidate_b is missing
        assert "candidate_a" not in result["missing_validation"]
        assert "candidate_b" in result["missing_validation"]

    def test_full_complete_scenario(self):
        """Full 2017-2024 validation + 2026 YTD for E_candidate_v2."""
        rows = []
        for year in REQUIRED_VALIDATION_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
                "information_ratio": 0.5,
                "annualized_return": 0.10,
            })
        for year in REQUIRED_YTD_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "ytd",
                "annualized_excess_return": 0.03,
                "information_ratio": 0.4,
                "annualized_return": 0.08,
            })
        df = pd.DataFrame(rows)
        result = check_completeness(df, ["E_candidate_v2"])
        assert result["is_complete"] is True
        assert result["issues"] == []


class TestComputeSummary:
    """Strategy summary computation."""

    def test_summary_with_full_data(self):
        """8 validation years → correct stats."""
        rows = []
        for i, year in enumerate(REQUIRED_VALIDATION_YEARS):
            excess = 0.01 * (i + 1)  # 0.01 to 0.08
            rows.append({
                "strategy": "test_strat",
                "year": year,
                "sample": "validation",
                "annualized_return": excess + 0.03,
                "annualized_excess_return": excess,
                "information_ratio": 0.3 + 0.05 * i,
                "avg_turnover": 0.5,
                "max_drawdown": -0.1,
            })
        df = pd.DataFrame(rows)
        summary = compute_summary(df, "test_strat")
        assert summary["n_years"] == 8
        assert summary["avg_excess"] > 0.03
        assert summary["pos_excess_years"] == 8  # all positive
        assert summary["avg_ir"] > 0.30

    def test_empty_subset_returns_empty_dict(self):
        """No data → empty dict."""
        df = pd.DataFrame(columns=["strategy", "year", "sample", "annualized_excess_return"])
        assert compute_summary(df, "nonexistent") == {}

    def test_summary_with_negative_years(self):
        """Mix of positive and negative years."""
        rows = []
        for i, year in enumerate([2020, 2021, 2022, 2023, 2024]):
            excess = 0.05 if i % 2 == 0 else -0.03
            rows.append({
                "strategy": "test_strat",
                "year": year,
                "sample": "validation",
                "annualized_return": excess + 0.05,
                "annualized_excess_return": excess,
                "information_ratio": 0.2 + 0.1 * i,
                "avg_turnover": 0.5,
                "max_drawdown": -0.1,
            })
        df = pd.DataFrame(rows)
        summary = compute_summary(df, "test_strat")
        assert summary["n_years"] == 5
        assert summary["pos_excess_years"] == 3
        assert summary["min_excess"] < 0
        assert summary["max_excess"] > 0


class TestComputeSummaryDrawdown:
    """Test drawdown-related fields in compute_summary."""

    def test_avg_max_drawdown(self):
        """avg_max_drawdown is the mean across years."""
        rows = []
        for i, year in enumerate(REQUIRED_VALIDATION_YEARS):
            rows.append({
                "strategy": "test_strat",
                "year": year,
                "sample": "validation",
                "annualized_return": 0.05,
                "annualized_excess_return": 0.03,
                "information_ratio": 0.4,
                "avg_turnover": 0.5,
                "max_drawdown": -0.05 - 0.01 * i,  # -5% to -12%
            })
        df = pd.DataFrame(rows)
        summary = compute_summary(df, "test_strat")
        assert "avg_max_drawdown" in summary
        assert summary["avg_max_drawdown"] < -0.05
        assert summary["avg_max_drawdown"] > -0.12

    def test_worst_max_drawdown(self):
        """worst_max_drawdown is the worst (most negative) across years."""
        rows = []
        for i, year in enumerate(REQUIRED_VALIDATION_YEARS):
            rows.append({
                "strategy": "test_strat",
                "year": year,
                "sample": "validation",
                "annualized_return": 0.05,
                "annualized_excess_return": 0.03,
                "information_ratio": 0.4,
                "avg_turnover": 0.5,
                "max_drawdown": -0.05 - 0.01 * i,  # -5% to -12%
            })
        df = pd.DataFrame(rows)
        summary = compute_summary(df, "test_strat")
        assert "worst_max_drawdown" in summary
        # The worst (most negative) should be the last one
        assert summary["worst_max_drawdown"] < -0.10

    def test_max_drawdown_columns_in_output(self):
        """Generated report includes both Avg Max DD and Worst Max DD columns."""
        from scripts.generate_go_nogo_decision import write_report
        import tempfile

        rows = []
        for year in REQUIRED_VALIDATION_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
                "information_ratio": 0.5,
                "annualized_return": 0.10,
                "avg_turnover": 0.4,
                "max_drawdown": -0.1,
            })
        for year in REQUIRED_YTD_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "ytd",
                "annualized_excess_return": 0.03,
                "information_ratio": 0.4,
                "annualized_return": 0.08,
                "avg_turnover": 0.3,
                "max_drawdown": -0.05,
            })
        df = pd.DataFrame(rows)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            out_path = Path(f.name)

        try:
            write_report(
                df, out_path,
                base_strategies=["A_5reversal"],
                candidate_strategies=["E_candidate_v2"],
                allow_incomplete=False,
            )
            content = out_path.read_text(encoding="utf-8")
            assert "Avg Max DD" in content
            assert "Worst Max DD" in content
            assert "Max DD" not in content.split("Avg Max DD")[0]  # "Max DD" alone should not appear
        finally:
            if out_path.exists():
                out_path.unlink()


class TestEvaluateThresholds:
    """GO/NO-GO threshold evaluation."""

    def test_all_pass(self):
        """Strong summary passes all thresholds."""
        summary = {
            "avg_excess": 0.05,
            "median_excess": 0.04,
            "pos_excess_years": 7,
            "avg_ir": 0.50,
            "min_excess": -0.05,
        }
        checks = evaluate_thresholds(summary)
        assert all(checks.values())

    def test_avg_excess_fails(self):
        """avg_excess below 2% → fails."""
        summary = {
            "avg_excess": 0.01,
            "median_excess": 0.01,
            "pos_excess_years": 6,
            "avg_ir": 0.50,
            "min_excess": -0.05,
        }
        checks = evaluate_thresholds(summary)
        assert not checks["avg_excess > 2%"]

    def test_pos_years_fails(self):
        """Less than 5 positive years → fails."""
        summary = {
            "avg_excess": 0.05,
            "median_excess": 0.04,
            "pos_excess_years": 3,
            "avg_ir": 0.50,
            "min_excess": -0.05,
        }
        checks = evaluate_thresholds(summary)
        assert not checks["pos_excess_years >= 5"]

    def test_avg_ir_fails(self):
        """avg_ir below 0.30 → fails."""
        summary = {
            "avg_excess": 0.05,
            "median_excess": 0.04,
            "pos_excess_years": 6,
            "avg_ir": 0.20,
            "min_excess": -0.05,
        }
        checks = evaluate_thresholds(summary)
        assert not checks["avg_ir > 0.30"]

    def test_max_loss_fails(self):
        """Max single-year loss below -10% → fails."""
        summary = {
            "avg_excess": 0.05,
            "median_excess": 0.04,
            "pos_excess_years": 6,
            "avg_ir": 0.50,
            "min_excess": -0.15,
        }
        checks = evaluate_thresholds(summary)
        assert not checks["max_excess_loss > -10%"]


class TestR2Inclusion:
    """G_candidate_v4_r2 must be in required strategies and enforced."""

    def test_r2_in_required_candidate_strategies(self):
        """REQUIRED_CANDIDATE_STRATEGIES includes G_candidate_v4_r2."""
        from scripts.generate_go_nogo_decision import REQUIRED_CANDIDATE_STRATEGIES
        assert "G_candidate_v4_r2" in REQUIRED_CANDIDATE_STRATEGIES, (
            "G_candidate_v4_r2 missing from REQUIRED_CANDIDATE_STRATEGIES"
        )

    def test_r2_in_main_candidate_list(self):
        """main() candidate_strategies must include G_candidate_v4_r2."""
        import inspect
        from scripts import generate_go_nogo_decision as mod
        source = inspect.getsource(mod.main)
        assert "G_candidate_v4_r2" in source, (
            "G_candidate_v4_r2 missing from main() candidate_strategies"
        )

    def test_missing_r2_causes_incomplete(self):
        """All other candidates complete but r2 missing → is_complete=False."""
        rows = []
        for strat in ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1"]:
            for year in REQUIRED_VALIDATION_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "validation",
                    "annualized_excess_return": 0.05, "information_ratio": 0.5,
                })
            for year in REQUIRED_YTD_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "ytd",
                    "annualized_excess_return": 0.03, "information_ratio": 0.4,
                })
        df = pd.DataFrame(rows)
        all_candidates = ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]
        result = check_completeness(df, all_candidates)
        assert result["is_complete"] is False
        assert "G_candidate_v4_r2" in result["missing_validation"]

    def test_missing_r2_causes_rejection(self):
        """Formal mode with r2 missing → SystemExit."""
        from scripts.generate_go_nogo_decision import write_report

        rows = []
        for strat in ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1"]:
            for year in REQUIRED_VALIDATION_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "validation",
                    "annualized_excess_return": 0.05, "information_ratio": 0.5,
                    "annualized_return": 0.10, "avg_turnover": 0.4, "max_drawdown": -0.1,
                })
            for year in REQUIRED_YTD_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "ytd",
                    "annualized_excess_return": 0.03, "information_ratio": 0.4,
                    "annualized_return": 0.08, "avg_turnover": 0.3, "max_drawdown": -0.05,
                })
        df = pd.DataFrame(rows)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            out_path = Path(f.name)
        try:
            with pytest.raises(SystemExit):
                write_report(
                    df, out_path,
                    base_strategies=["A_5reversal"],
                    candidate_strategies=["E_candidate_v2", "F_candidate_v3",
                                          "G_candidate_v4_r1", "G_candidate_v4_r2"],
                    allow_incomplete=False,
                )
        finally:
            if out_path.exists():
                out_path.unlink()

    def test_r2_missing_years_causes_incomplete(self):
        """r2 present but only has 1 validation year → incomplete."""
        rows = [{
            "strategy": "G_candidate_v4_r2", "year": 2024, "sample": "validation",
            "annualized_excess_return": 0.05, "information_ratio": 0.5,
        }]
        for strat in ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1"]:
            for year in REQUIRED_VALIDATION_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "validation",
                    "annualized_excess_return": 0.05, "information_ratio": 0.5,
                })
            for year in REQUIRED_YTD_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "ytd",
                    "annualized_excess_return": 0.03, "information_ratio": 0.4,
                })
        df = pd.DataFrame(rows)
        all_candidates = ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]
        result = check_completeness(df, all_candidates)
        assert result["is_complete"] is False
        assert len(result["missing_validation"].get("G_candidate_v4_r2", [])) >= 7

    def test_complete_r2_data_passes(self):
        """All candidates complete including r2 → is_complete=True."""
        rows = []
        for strat in ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]:
            for year in REQUIRED_VALIDATION_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "validation",
                    "annualized_excess_return": 0.05, "information_ratio": 0.5,
                })
            for year in REQUIRED_YTD_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "ytd",
                    "annualized_excess_return": 0.03, "information_ratio": 0.4,
                })
        df = pd.DataFrame(rows)
        all_candidates = ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]
        result = check_completeness(df, all_candidates)
        assert result["is_complete"] is True
        assert len(result["issues"]) == 0

    def test_document_contains_r2_when_present(self):
        """Complete data → generated doc includes G_candidate_v4_r2."""
        from scripts.generate_go_nogo_decision import write_report

        rows = []
        for strat in ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]:
            for year in REQUIRED_VALIDATION_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "validation",
                    "annualized_excess_return": 0.05, "information_ratio": 0.35,
                    "annualized_return": 0.08, "avg_turnover": 0.4, "max_drawdown": -0.1,
                })
            for year in REQUIRED_YTD_YEARS:
                rows.append({
                    "strategy": strat, "year": year, "sample": "ytd",
                    "annualized_excess_return": 0.03, "information_ratio": 0.4,
                    "annualized_return": 0.08, "avg_turnover": 0.3, "max_drawdown": -0.05,
                })
        df = pd.DataFrame(rows)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            out_path = Path(f.name)
        try:
            write_report(
                df, out_path,
                base_strategies=["A_5reversal"],
                candidate_strategies=["E_candidate_v2", "F_candidate_v3",
                                      "G_candidate_v4_r1", "G_candidate_v4_r2"],
                allow_incomplete=False,
            )
            content = out_path.read_text(encoding="utf-8")
            assert "G_candidate_v4_r2" in content
            assert "INCOMPLETE" not in content
        finally:
            if out_path.exists():
                out_path.unlink()


class TestAllowIncomplete:
    """--allow-incomplete flag behavior."""

    def test_refuses_without_allow_incomplete(self):
        """SystemExit when data is incomplete and --allow-incomplete not set."""
        from scripts.generate_go_nogo_decision import write_report
        import tempfile

        # Minimal incomplete data
        df = pd.DataFrame([{
            "strategy": "E_candidate_v2",
            "year": 2023,
            "sample": "validation",
            "annualized_excess_return": 0.05,
            "information_ratio": 0.3,
        }])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            out_path = Path(f.name)

        try:
            with pytest.raises(SystemExit):
                write_report(
                    df, out_path,
                    base_strategies=["A_5reversal"],
                    candidate_strategies=["E_candidate_v2"],
                    allow_incomplete=False,
                )
        finally:
            if out_path.exists():
                out_path.unlink()

    def test_allows_with_allow_incomplete(self):
        """allow_incomplete=True generates document with INCOMPLETE tag."""
        from scripts.generate_go_nogo_decision import write_report
        import tempfile

        df = pd.DataFrame([{
            "strategy": "E_candidate_v2",
            "year": 2023,
            "sample": "validation",
            "annualized_excess_return": 0.05,
            "information_ratio": 0.3,
            "annualized_return": 0.08,
            "avg_turnover": 0.4,
            "max_drawdown": -0.1,
        }])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            out_path = Path(f.name)

        try:
            write_report(
                df, out_path,
                base_strategies=[],
                candidate_strategies=["E_candidate_v2"],
                allow_incomplete=True,
            )
            content = out_path.read_text(encoding="utf-8")
            assert "INCOMPLETE" in content
        finally:
            if out_path.exists():
                out_path.unlink()

    def test_complete_data_no_warning(self):
        """Complete data does not trigger INCOMPLETE warning."""
        from scripts.generate_go_nogo_decision import write_report
        import tempfile

        rows = []
        for year in REQUIRED_VALIDATION_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "validation",
                "annualized_excess_return": 0.05,
                "information_ratio": 0.5,
                "annualized_return": 0.10,
                "avg_turnover": 0.4,
                "max_drawdown": -0.1,
            })
        for year in REQUIRED_YTD_YEARS:
            rows.append({
                "strategy": "E_candidate_v2",
                "year": year,
                "sample": "ytd",
                "annualized_excess_return": 0.03,
                "information_ratio": 0.4,
                "annualized_return": 0.08,
                "avg_turnover": 0.3,
                "max_drawdown": -0.05,
            })
        df = pd.DataFrame(rows)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            out_path = Path(f.name)

        try:
            write_report(
                df, out_path,
                base_strategies=["A_5reversal"],
                candidate_strategies=["E_candidate_v2"],
                allow_incomplete=False,
            )
            content = out_path.read_text(encoding="utf-8")
            assert "INCOMPLETE" not in content
        finally:
            if out_path.exists():
                out_path.unlink()
