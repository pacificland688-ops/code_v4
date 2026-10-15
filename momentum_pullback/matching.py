"""Lock signal-time controls without inspecting any outcome or fill columns."""
from __future__ import annotations

import numpy as np
import pandas as pd

from momentum_pullback.contracts import Contract, GateError
from momentum_pullback.data_adapter import unique_keys
from momentum_pullback.features import average_rank_percentiles

MATCH_COLUMNS = ["event_id", "signal_date", "event_code", "control_code", "control_rank", "distance", "contract_hash"]


def lock_matches(events: pd.DataFrame, features: pd.DataFrame, observations: pd.DataFrame, contract: Contract) -> dict:
    cfg = contract.section("matching")
    covariates = cfg["covariates"]
    percentile_columns = ["pct_" + column for column in covariates]
    needed = {"ts_code", "trade_date", "signal_cutoff", "strong_status", "rank_denominator_complete", "in_rank_denominator", "rank_denominator_hash", "membership_known", "is_member", "st_known", "is_st", "price_history_known", "valid_observations", "industry_code", "industry_available_at", "basic_available_at", "contract_hash", *covariates, *percentile_columns}
    if not needed.issubset(features):
        raise GateError("MATCH_INPUT_SCHEMA_MISSING", sorted(needed - set(features)))
    unique_keys(features, ["ts_code", "trade_date"], "match_features")
    unique_keys(events, ["event_id"], "match_events")
    if not features.contract_hash.eq(contract.hash).all() or not events.contract_hash.eq(contract.hash).all():
        raise GateError("MATCH_CONTRACT_MISMATCH")
    for column in ["rank_denominator_complete", "in_rank_denominator", "membership_known", "is_member", "st_known", "is_st", "price_history_known"]:
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
        def fail(reason):
            failures.append({"event_id": event.event_id, "signal_date": event.signal_date, "reason": reason})
        minimum = contract.section("features")["min_price_observations"]
        ranked = day[day.in_rank_denominator] if not day.empty else day
        if day.empty or not bool(day.rank_denominator_complete.all()) or ranked.empty:
            fail("RANK_DENOMINATOR_INCOMPLETE")
            continue
        members = day[day.membership_known & day.is_member & day.st_known & ~day.is_st & day.price_history_known & day.valid_observations.ge(minimum)]
        same_names = set(ranked.ts_code.astype(str)) == set(members.ts_code.astype(str))
        one_hash = not ranked.rank_denominator_hash.isna().any() and ranked.rank_denominator_hash.nunique() == 1
        if not same_names or not one_hash:
            raise GateError("MATCH_DENOMINATOR_MISMATCH", {"signal_date": int(event.signal_date), "ranked": int(ranked.ts_code.nunique()), "members": int(members.ts_code.nunique())})
        if not np.isfinite(ranked[covariates].to_numpy(dtype=float)).all():
            fail("MATCH_COVARIATES_INCOMPLETE")
            continue
        cutoff = pd.to_datetime(event.signal_cutoff, utc=True)
        if not pd.to_datetime(day.signal_cutoff, utc=True).eq(cutoff).all():
            fail("EVENT_AND_FEATURE_CUTOFF_MISMATCH")
            continue
        industry_times = pd.to_datetime(ranked.industry_available_at, utc=True, errors="coerce")
        basic_times = pd.to_datetime(ranked.basic_available_at, utc=True, errors="coerce")
        if ranked.industry_code.isna().any() or industry_times.isna().any() or basic_times.isna().any() or (industry_times > cutoff).any() or (basic_times > cutoff).any():
            fail("MATCH_INFORMATION_UNAVAILABLE_AT_CUTOFF")
            continue
        percentages = average_rank_percentiles(ranked, covariates)
        stored = ranked[percentile_columns].to_numpy(dtype=float)
        if not np.allclose(stored, percentages.to_numpy(dtype=float), rtol=0, atol=0):
            raise GateError("MATCH_PERCENTILE_IDENTITY_MISMATCH", {"signal_date": int(event.signal_date)})
        own = ranked[ranked.ts_code.eq(event.ts_code)]
        if len(own) != 1:
            fail("EVENT_NOT_IN_VERIFIED_DENOMINATOR")
            continue
        own_index = own.index[0]
        pool = ranked[ranked.strong_status.eq("KNOWN_ELIGIBLE") & ranked.industry_code.eq(own.iloc[0].industry_code) & ranked.identity_known.fillna(False) & ranked.in_touch_segment.eq(False) & ~ranked.ts_code.eq(event.ts_code)].copy()
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
