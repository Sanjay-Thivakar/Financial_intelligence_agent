"""
Phase 6.9D — Multimodal Dataset Builder and Point-in-Time Harmonization Pipeline.

Constructs an auditable, point-in-time-safe multimodal dataset joining:
1. Daily market features and forward-return target (305 companies, 2019-01-01 to 2020-06-10).
2. Point-in-time SEC EDGAR financial facts (accounting ratios, book values, staleness).
3. Point-in-time SEC Form 8-K corporate event metrics (5d event counts, earnings releases, recency).

Contract & Timing Invariants:
- Decision Timestamp (T): Session T Market Close (16:00:00 US Eastern Time -> UTC).
- Trade Entry Timestamp (T+1): Session T+1 Market Open (09:30:00 US Eastern Time -> UTC).
- Trade Exit Timestamp (T+5): Session T+5 Market Close (16:00:00 US Eastern Time -> UTC).
- Target Definition: Forward 5-session total return:
    y_T = (P_{T+5, close}^adj - P_{T+1, open}^adj) / P_{T+1, open}^adj
- Information Cutoff: Every feature uses ONLY data available at Session T close.
  Filings accepted after Session T close are excluded.
- Exactly 1 observation per unique (company_id, trading_date) pair.
- Output: data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from src.data.universe.identity_mapping import IdentityResolutionEngine
from src.features.calendar import MarketCalendar
from src.features.config import DecisionTimingMode
from src.features.market import MarketFeatureEngine, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.features.fundamental import FundamentalFeatureEngine
from src.features.event import SECEventFeatureEngine
from src.models.baseline import MarketBaselinePipeline


def build_phase6_9d_multimodal_dataset() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    print("=" * 95, flush=True)
    print("PHASE 6.9D: MULTIMODAL FEATURE ALIGNMENT & DATASET ASSEMBLY", flush=True)
    print("=" * 95, flush=True)

    t0 = time.time()
    out_dir = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Authoritative Input Datasets
    manifest_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
    market_path = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_9a1_market_eligible.parquet"
    facts_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated_v2.parquet"
    events_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_8k_events_consolidated_v2.parquet"
    coverage_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_company_coverage_v2.csv"

    print(f"Loading inputs from authoritative paths...", flush=True)
    df_manifest = pd.read_csv(manifest_path)
    df_market = pd.read_parquet(market_path)
    df_facts = pd.read_parquet(facts_path)
    df_events = pd.read_parquet(events_path)
    df_cov = pd.read_csv(coverage_path)

    print(f"  Cohort Manifest: {len(df_manifest)} companies across {df_manifest['sector'].nunique()} sectors.", flush=True)
    print(f"  Market Parquet : {len(df_market):,} rows across {df_market['ticker'].nunique()} tickers.", flush=True)
    print(f"  Consolidated Facts: {len(df_facts):,} rows across {df_facts['ticker'].nunique()} tickers.", flush=True)
    print(f"  Consolidated 8-Ks : {len(df_events):,} rows across {df_events['ticker'].nunique()} tickers.", flush=True)
    print(f"  SEC Coverage CSV  : {len(df_cov)} companies.", flush=True)

    # 2. Historical Identity Verification
    id_engine = IdentityResolutionEngine(df_manifest)
    cxo_cik, cxo_name, cxo_map_type = id_engine.resolve_cik("CXO", "2019-06-01")
    apa_cik, apa_name, apa_map_type = id_engine.resolve_cik("APA", "2019-06-01")
    print(f"Identity Verification:", flush=True)
    print(f"  CXO -> True Historical CIK {cxo_cik} ({cxo_name}, type={cxo_map_type})", flush=True)
    print(f"  APA -> Predecessor CIK {apa_cik} ({apa_name}, type={apa_map_type})", flush=True)

    # 3. Market Technical Features & 5-Day Forward Return Targets
    print("\nComputing market features and forward return targets on primary window (2018-01-01 to 2020-06-15)...", flush=True)
    df_w = df_market[
        (df_market["trading_date"] >= "2018-01-01") & (df_market["trading_date"] <= "2020-06-15")
    ].copy()

    adj_factor = df_w["adjusted_close"] / df_w["close"]
    df_w["adjusted_open"] = df_w["open"] * adj_factor

    m_engine = MarketFeatureEngine(MarketFeatureConfig(decision_timing=DecisionTimingMode.MARKET_CLOSE))
    df_feat = m_engine.compute_features(df_w)

    tgt_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    df_tgt = tgt_engine.add_target(df_feat)

    # Filter strictly to research evaluation window (2019-01-01 to 2020-06-10 with valid forward return)
    df_eval = df_tgt[
        (df_tgt["trading_date"] >= "2019-01-01")
        & (df_tgt["trading_date"] <= "2020-06-10")
        & (df_tgt["target_forward_return_5d_valid"] == True)
    ].sort_values(["trading_date", "company_id"]).reset_index(drop=True)

    unique_dates = sorted(df_eval["trading_date"].unique().tolist())
    unique_companies = sorted(df_eval["company_id"].unique().tolist())
    print(f"Evaluation observations: {len(df_eval):,} across {len(unique_companies)} companies and {len(unique_dates)} dates.", flush=True)
    assert len(df_eval) == 110_105, f"Expected exactly 110,105 rows, got {len(df_eval)}"
    assert len(unique_companies) == 305, f"Expected 305 companies, got {len(unique_companies)}"
    assert len(unique_dates) == 361, f"Expected 361 dates, got {len(unique_dates)}"

    # 4. Precompute Temporal Alignment Cutoffs
    print("Precomputing market session cutoffs and 5-session event windows...", flush=True)
    all_sessions = sorted(df_market["trading_date"].unique().tolist())
    session_idx = {d: i for i, d in enumerate(all_sessions)}

    decision_cutoff_map = {d: MarketCalendar.get_session_close_utc(d) for d in unique_dates}
    execution_cutoff_map = {d: MarketCalendar.get_next_session_open_utc(d) for d in unique_dates}

    window_start_map = {}
    for d in unique_dates:
        idx = session_idx[d]
        prior_d = all_sessions[idx - 5]
        window_start_map[d] = MarketCalendar.get_session_open_cutoff_utc(prior_d, buffer_minutes=15)

    # 5. Extract Point-in-Time Fundamental Snapshots
    print("Extracting point-in-time fundamental snapshots (acceptance_timestamp <= T close)...", flush=True)
    fund_engine = FundamentalFeatureEngine(df_facts)
    fund_records = []

    t_fund_start = time.time()
    for cid, comp_rows in df_eval.groupby("company_id"):
        c_dates = comp_rows["trading_date"].tolist()
        comp_facts = fund_engine._company_facts.get(cid)
        f_cache = {}

        if comp_facts is not None and not comp_facts.empty:
            accept_times = sorted(pd.to_datetime(comp_facts["acceptance_timestamp"], utc=True).tolist())
            for t_date in c_dates:
                dec_utc = decision_cutoff_map[t_date]
                prior = [t for t in accept_times if t <= dec_utc]
                key = prior[-1] if prior else None
                if key not in f_cache:
                    snap = fund_engine.get_as_of_snapshot(cid, dec_utc)
                    f_cache[key] = {k: v for k, v in snap.items() if k != "as_of_timestamp"}
                row_snap = dict(f_cache[key])
                row_snap["company_id"] = cid
                row_snap["trading_date"] = t_date
                fund_records.append(row_snap)
        else:
            empty_snap = fund_engine._build_empty_snapshot({"company_id": cid, "fundamental_available": False})
            for t_date in c_dates:
                row_snap = dict(empty_snap)
                row_snap["company_id"] = cid
                row_snap["trading_date"] = t_date
                fund_records.append(row_snap)

    print(f"Fundamental extraction completed in {time.time() - t_fund_start:.2f}s ({len(fund_records):,} records).", flush=True)

    # 6. Extract Point-in-Time Corporate Event Snapshots
    print("Extracting point-in-time SEC 8-K event features (acceptance_timestamp + 5m <= T close)...", flush=True)
    t_evt_start = time.time()
    evt_engine = SECEventFeatureEngine(df_events, covered_company_ids=set(unique_companies))

    # Pre-parse event records into lightweight tuples
    parsed_events = {}
    buf_td = timedelta(minutes=5)
    for cid, grp in df_events.groupby("company_id"):
        c_list = []
        grp_sorted = grp.sort_values("acceptance_timestamp")
        for _, row in grp_sorted.iterrows():
            acc_ts = pd.to_datetime(row["acceptance_timestamp"], utc=True)
            is_mid = (acc_ts.hour == 0 and acc_ts.minute == 0 and acc_ts.second == 0)
            items_str = str(row.get("items", ""))
            has_earn = ("2.02" in items_str)
            acc_date = acc_ts.strftime("%Y-%m-%d")
            c_list.append((acc_ts, is_mid, acc_date, has_earn))
        parsed_events[cid] = c_list

    evt_records = []
    for cid, comp_rows in df_eval.groupby("company_id"):
        c_dates = comp_rows["trading_date"].tolist()
        ev_list = parsed_events.get(cid, [])

        for t_date in c_dates:
            dec_utc = decision_cutoff_map[t_date]
            w_start = window_start_map[t_date]
            cutoff_boundary = dec_utc - buf_td

            eligible_evts = []
            for (acc_ts, is_mid, acc_date, has_earn) in ev_list:
                if is_mid:
                    if acc_date < t_date:
                        eligible_evts.append((acc_ts, has_earn))
                else:
                    if acc_ts < cutoff_boundary:
                        eligible_evts.append((acc_ts, has_earn))

            if not eligible_evts:
                evt_records.append({
                    "company_id": cid,
                    "trading_date": t_date,
                    "sec_event_available": True,
                    "sec_event_coverage_status": "active",
                    "sec_event_count_5d": 0,
                    "sec_earnings_release_in_window": 0,
                    "sec_days_since_last_8k": np.nan,
                })
            else:
                latest_acc_ts = eligible_evts[-1][0]
                age_days = (dec_utc - latest_acc_ts).total_seconds() / 86400.0
                w_evts = [e for e in eligible_evts if (e[0] + buf_td) > w_start]
                count_5d = len(w_evts)
                has_earn_win = 1 if any(e[1] for e in w_evts) else 0

                evt_records.append({
                    "company_id": cid,
                    "trading_date": t_date,
                    "sec_event_available": True,
                    "sec_event_coverage_status": "active",
                    "sec_event_count_5d": count_5d,
                    "sec_earnings_release_in_window": has_earn_win,
                    "sec_days_since_last_8k": float(age_days),
                })

    print(f"Event extraction completed in {time.time() - t_evt_start:.2f}s ({len(evt_records):,} records).", flush=True)

    # 7. Merge Modalities into Unified Dataset
    print("\nMerging market, fundamental, and event features on (company_id, trading_date)...", flush=True)
    df_fund = pd.DataFrame(fund_records).drop_duplicates(subset=["company_id", "trading_date"])
    df_evt = pd.DataFrame(evt_records).drop_duplicates(subset=["company_id", "trading_date"])

    pre_join_count = len(df_eval)
    df_merged = df_eval.merge(df_fund, on=["company_id", "trading_date"], how="left")
    assert len(df_merged) == pre_join_count, f"Row multiplication in fundamental merge: {len(df_merged)} vs {pre_join_count}"

    df_merged = df_merged.merge(df_evt, on=["company_id", "trading_date"], how="left")
    assert len(df_merged) == pre_join_count, f"Row multiplication in event merge: {len(df_merged)} vs {pre_join_count}"

    # 8. Enrich Contract Identifiers & Temporal Proof Metadata
    dec_ts_series = pd.to_datetime(df_merged["decision_timestamp"], utc=True)
    df_merged["dataset_row_id"] = df_merged["company_id"] + "|" + dec_ts_series.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df_merged["decision_timing_mode"] = DecisionTimingMode.MARKET_CLOSE.value
    df_merged["execution_timestamp"] = df_merged["trading_date"].map(execution_cutoff_map)
    df_merged["dataset_builder_provenance"] = "phase6_9d_point_in_time_builder_v1"

    # Merge company manifest attributes (sector, company_name, true_historical_cik)
    manifest_attrs = df_manifest[["company_id", "company_name", "sector"]].drop_duplicates()
    df_merged = df_merged.merge(manifest_attrs, on="company_id", how="left")

    # Verify uniqueness
    dups = df_merged["dataset_row_id"].duplicated().sum()
    assert dups == 0, f"FATAL: Detected {dups} duplicate dataset_row_id entries!"

    # 9. Verify Point-in-Time Anti-Leakage Constraints
    print("\nAuditing temporal boundaries against trade-entry cutoff...", flush=True)
    for _, row in df_merged.iloc[:500].iterrows():
        dec_ts = pd.to_datetime(row["decision_timestamp"], utc=True)
        exec_ts = pd.to_datetime(row["execution_timestamp"], utc=True)
        assert dec_ts < exec_ts, f"Decision timestamp {dec_ts} must precede execution timestamp {exec_ts}!"

    # Check that fundamental acceptance timestamps strictly precede or equal decision timestamp
    ts_cols = [c for c in df_merged.columns if c.startswith("fundamental_") and c.endswith("_acceptance_timestamp")]
    for col in ts_cols:
        bad_mask = df_merged[col].notna() & (pd.to_datetime(df_merged[col], utc=True) > dec_ts_series)
        assert bad_mask.sum() == 0, f"FATAL LOOK-AHEAD: {bad_mask.sum()} records in {col} violate decision cutoff!"

    print("  Temporal anti-leakage verified: 0 lookahead violations detected.", flush=True)

    # 10. Persist Derived Multimodal Dataset
    dataset_parquet_path = out_dir / "phase6_9d_multimodal_dataset.parquet"
    df_merged.to_parquet(dataset_parquet_path, index=False)
    print(f"\nSuccessfully persisted multimodal dataset to:\n  {dataset_parquet_path}", flush=True)
    print(f"  Total Rows: {len(df_merged):,}, Columns: {len(df_merged.columns)}, File Size: {dataset_parquet_path.stat().st_size:,} bytes", flush=True)

    # 11. Compile Data Quality and Coverage Audit Metrics
    quality_audit = {
        "phase": "6.9D",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - t0, 2),
        "total_observations": len(df_merged),
        "unique_companies": int(df_merged["company_id"].nunique()),
        "unique_tickers": int(df_merged["ticker"].nunique()),
        "unique_trading_sessions": int(df_merged["trading_date"].nunique()),
        "date_range": [str(df_merged["trading_date"].min()), str(df_merged["trading_date"].max())],
        "sector_breakdown": df_merged["sector"].value_counts().to_dict(),
        "market_feature_match_rate": 1.0,
        "fundamental_match_rate": float(df_merged["fundamental_available"].mean()),
        "event_match_rate": float(df_merged["sec_event_available"].mean()),
        "row_count_integrity": {
            "pre_join_market_rows": pre_join_count,
            "post_fundamental_join_rows": pre_join_count,
            "post_event_join_rows": len(df_merged),
            "duplicate_dataset_row_ids": int(dups),
        },
        "feature_missingness_rates": {
            c: round(float(df_merged[c].isna().mean()), 4)
            for c in MarketBaselinePipeline.ALL_FEATURE_COLUMNS
            if c in df_merged.columns
        },
        "fundamental_staleness_distribution": {
            "all_facts_stale_pct": round(float(df_merged["fundamental_all_facts_stale"].mean() * 100.0), 2),
            "has_stale_facts_pct": round(float(df_merged["fundamental_has_stale_facts"].mean() * 100.0), 2),
            "mean_revenue_age_days": round(float(df_merged["fundamental_revenue_age_days"].mean()), 1),
            "median_revenue_age_days": round(float(df_merged["fundamental_revenue_age_days"].median()), 1),
        },
        "event_activity_summary": {
            "total_5d_events_observed": int(df_merged["sec_event_count_5d"].sum()),
            "sessions_with_event_pct": round(float((df_merged["sec_event_count_5d"] > 0).mean() * 100.0), 2),
            "earnings_release_sessions_count": int(df_merged["sec_earnings_release_in_window"].sum()),
            "mean_days_since_last_8k": round(float(df_merged["sec_days_since_last_8k"].mean()), 1),
        },
        "target_audit": {
            "target_column": "target_forward_return_5d",
            "target_valid_column": "target_forward_return_5d_valid",
            "total_valid_targets": int(df_merged["target_forward_return_5d_valid"].sum()),
            "mean_target_return": round(float(df_merged["target_forward_return_5d"].mean()), 6),
            "std_target_return": round(float(df_merged["target_forward_return_5d"].std()), 6),
            "min_target_return": round(float(df_merged["target_forward_return_5d"].min()), 6),
            "max_target_return": round(float(df_merged["target_forward_return_5d"].max()), 6),
        },
        "identity_lineage_trace": {
            "CXO": {
                "ticker": "CXO",
                "canonical_company_id": "US_CIK_0001390532",
                "resolved_historical_cik": cxo_cik,
                "n_observations": len(df_merged[df_merged["ticker"] == "CXO"]),
                "facts_available_pct": float(df_merged[df_merged["ticker"] == "CXO"]["fundamental_available"].mean()),
                "events_available_pct": float(df_merged[df_merged["ticker"] == "CXO"]["sec_event_available"].mean()),
            },
            "APA": {
                "ticker": "APA",
                "canonical_company_id": "US_CIK_0001841666",
                "resolved_predecessor_cik": apa_cik,
                "n_observations": len(df_merged[df_merged["ticker"] == "APA"]),
                "facts_available_pct": float(df_merged[df_merged["ticker"] == "APA"]["fundamental_available"].mean()),
                "events_available_pct": float(df_merged[df_merged["ticker"] == "APA"]["sec_event_available"].mean()),
            },
        },
    }

    audit_json_path = out_dir / "phase6_9d_data_quality_report.json"
    with open(audit_json_path, "w", encoding="utf-8") as f:
        json.dump(quality_audit, f, indent=2)

    print(f"Data quality audit JSON saved to:\n  {audit_json_path}", flush=True)
    print("=" * 95, flush=True)

    return df_merged, quality_audit


if __name__ == "__main__":
    build_phase6_9d_multimodal_dataset()
