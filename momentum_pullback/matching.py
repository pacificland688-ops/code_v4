"""Lock signal-time controls without inspecting any outcome or fill columns."""
from __future__ import annotations

import numpy as np
import pandas as pd

from momentum_pullback.contracts import Contract, GateError
from momentum_pullback.data_adapter import unique_keys

MATCH_COLUMNS = ["event_id", "signal_date", "event_code", "control_code", "control_rank", "distance", "contract_hash"]


def lock_matches(events: pd.DataFrame, features: pd.DataFrame, observations: pd.DataFrame, contract: Contract) -> dict:
    cfg = contract.section("matching")
    covariates = cfg["covariates"]
    needed = {"ts_code", "trade_date", "signal_cutoff", "strong_status", "rank_denominator_complete", "membership_known", "is_member", "st_known", "is_st", "price_history_known", "valid_observations", "industry_code", "industry_available_at", "basic_available_at", "contract_hash", *covariates}
    if not needed.issubset(features):
        raise GateError("MATCH_INPUT_SCHEMA_MISSING", sorted(needed - set(features)))
    unique_keys(features, ["ts_code", "trade_date"], "match_features")
    unique_keys(events, ["event_id"], "match_events")
    if not features.contract_hash.eq(contract.hash).all() or not events.contract_hash.eq(contract.hash).all():
        raise GateError("MATCH_CONTRACT_MISMATCH")
    for column in ["rank_denominator_complete", "membership_known", "is_member", "st_known", "is_st", "price_history_known"]:
        if not features[column].map(lambda value: isinstance(value, (bool, np.bool_))).all():
            raise GateError("MATCH_BOOLEAN_STATE_INVALID", column)
    unique_keys(observations, ["ts_code", "trade_date"], "touch_observations")
    merged = features.merge(observations[["ts_code", "trade_date", "in_touch_segment", "identity_known"]], on=["ts_code", "trade_date"], validate="one_to_one", how="left")
    matches, failures, balances = [], [], []
    candidate_count = 0
    for event in events.itertuples(index=False):
        if event.event_status not in {"FIRST_CANDIDATE", "LATER_CANDIDATE"}:
            continue
        candidate_count += 1
        day = merged[merged.trade_date.eq(event.signal_date)].copy()
        denominator = day[day.membership_known & day.is_member & day.st_known & ~day.is_st & day.price_history_known & day.valid_observations.ge(contract.section("features")["min_price_observations"])]
        def fail(reason):
            failures.append({"event_id": event.event_id, "signal_date": event.signal_date, "reason": reason})
        if day.empty or not bool(day.rank_denominator_complete.all()) or denominator.empty:
            fail("RANK_DENOMINATOR_INCOMPLETE")
            continue
        if not np.isfinite(denominator[covariates].to_numpy(dtype=float)).all():
            fail("MATCH_COVARIATES_INCOMPLETE")
            continue
        cutoff = pd.to_datetime(event.signal_cutoff, utc=True)
        if not pd.to_datetime(day.signal_cutoff, utc=True).eq(cutoff).all():
            fail("EVENT_AND_FEATURE_CUTOFF_MISMATCH")
            continue
        industry_times = pd.to_datetime(denominator.industry_available_at, utc=True, errors="coerce")
        basic_times = pd.to_datetime(denominator.basic_available_at, utc=True, errors="coerce")
        if denominator.industry_code.isna().any() or industry_times.isna().any() or basic_times.isna().any() or (industry_times > cutoff).any() or (basic_times > cutoff).any():
            fail("MATCH_INFORMATION_UNAVAILABLE_AT_CUTOFF")
            continue
        percentages = denominator[covariates].rank(method="average", pct=True)
        own = denominator[denominator.ts_code.eq(event.ts_code)]
        if len(own) != 1:
            fail("EVENT_NOT_IN_VERIFIED_DENOMINATOR")
            continue
        own_index = own.index[0]
        pool = denominator[denominator.strong_status.eq("KNOWN_ELIGIBLE") & denominator.industry_code.eq(own.iloc[0].industry_code) & denominator.identity_known.fillna(False) & denominator.in_touch_segment.eq(False) & ~denominator.ts_code.eq(event.ts_code)].copy()
        differences = percentages.loc[pool.index] - percentages.loc[own_index]
        pool["distance"] = differences.pow(2).mean(axis=1)
        pool = pool[differences.abs().le(cfg["caliper"]).all(axis=1)].sort_values(["distance", "ts_code"], kind="stable")
        if len(pool) < cfg["controls"]:
            fail("MATCH_FAILED_INSUFFICIENT_CONTROLS")
            continue
        for rank, row in enumerate(pool.head(cfg["controls"]).itertuples(), 1):
            matches.append({"event_id": event.event_id, "signal_date": event.signal_date, "event_code": event.ts_code, "control_code": row.ts_code, "control_rank": rank, "distance": float(row.distance), "contract_hash": contract.hash})
            for covariate in covariates:
                balances.append({"event_id": event.event_id, "control_code": row.ts_code, "covariate": covariate, "event_percentile": float(percentages.loc[own_index, covariate]), "control_percentile": float(percentages.loc[row.Index, covariate]), "percentile_difference": float(percentages.loc[row.Index, covariate] - percentages.loc[own_index, covariate])})
    frame = pd.DataFrame(matches, columns=MATCH_COLUMNS)
    failed = pd.DataFrame(failures, columns=["event_id", "signal_date", "reason"])
    if not failed.empty:
        status = "MATCHING_PARTIALLY_UNEVALUABLE" if not frame.empty else "MATCHING_UNEVALUABLE"
    elif frame.empty:
        status = "NO_MATCHABLE_CANDIDATES"
    else:
        status = "MATCHES_LOCKED"
    return {"status": status, "matches": frame, "failures": failed, "balance": pd.DataFrame(balances, columns=["event_id", "control_code", "covariate", "event_percentile", "control_percentile", "percentile_difference"]), "coverage": {"candidate_events": candidate_count, "matched_events": frame.event_id.nunique(), "failed_events": len(failed)}, "reuse": frame.groupby(["signal_date", "control_code"]).size().rename("reuse_count").reset_index() if not frame.empty else pd.DataFrame(columns=["signal_date", "control_code", "reuse_count"])}
