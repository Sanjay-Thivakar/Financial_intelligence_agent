"""
Phase 8R.1 — Final Temporal Integrity & Economic Calculation Verification Engine.

Performs:
1. Audit A: Full timezone-aware verification of market close conversions, DST transitions,
   intraday boundaries, after-hours quarantines, weekend/holiday filings, and restatement isolation.
2. Audit B: Rigorous audit of portfolio construction, dollar neutrality, empirical vs standardized
   turnover, transaction cost deductions, staggered 5-session position arithmetic, and Sharpe metrics.
"""

import json
import os
import sys
import time
from datetime import datetime, date
import zoneinfo
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.sec.point_in_time import (
    get_market_close_utc,
    get_pre_open_cutoff_utc,
    is_record_eligible_for_trade,
    is_record_eligible_at_cutoff,
    NY_TZ,
    UTC_TZ,
)
from src.features.financial_reports import Phase8FinancialReportEngine

HOLDOUT_PREDS_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_final_holdout.parquet"
DEV_PREDS_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_development.parquet"
RESULTS_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_experiment_results.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "research" / "phase8"


def run_temporal_audit_a() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("AUDIT A: DAYLIGHT-SAVING & POINT-IN-TIME TIMESTAMP INTEGRITY")
    print("=" * 80)
    results = {}

    # 1. Normal Winter Trading Date (EST: UTC-5)
    # 2021-01-15 -> 16:00 ET = 21:00 UTC
    winter_date = "2021-01-15"
    close_winter = get_market_close_utc(winter_date)
    ny_winter = close_winter.tz_convert(NY_TZ)
    offset_winter = ny_winter.utcoffset().total_seconds() / 3600.0
    print(f"1. Normal Winter Date ({winter_date}):")
    print(f"   UTC Close: {close_winter} | NY Local: {ny_winter} | Offset: {offset_winter}h (Expected: -5.0h, 21:00 UTC)")
    assert close_winter.hour == 21 and offset_winter == -5.0
    results["winter_close_utc"] = str(close_winter)

    # 2. Normal Summer Trading Date (EDT: UTC-4)
    # 2021-07-15 -> 16:00 ET = 20:00 UTC
    summer_date = "2021-07-15"
    close_summer = get_market_close_utc(summer_date)
    ny_summer = close_summer.tz_convert(NY_TZ)
    offset_summer = ny_summer.utcoffset().total_seconds() / 3600.0
    print(f"2. Normal Summer Date ({summer_date}):")
    print(f"   UTC Close: {close_summer} | NY Local: {ny_summer} | Offset: {offset_summer}h (Expected: -4.0h, 20:00 UTC)")
    assert close_summer.hour == 20 and offset_summer == -4.0
    results["summer_close_utc"] = str(close_summer)

    # 3. US Spring Daylight-Saving Transition (March 2021)
    # DST transition occurred Sunday, March 14, 2021
    # Friday before DST: 2021-03-12 (EST, UTC-5)
    # Monday after DST:  2021-03-15 (EDT, UTC-4)
    fri_spring = get_market_close_utc("2021-03-12")
    mon_spring = get_market_close_utc("2021-03-15")
    print(f"3. US Spring DST Transition (March 2021):")
    print(f"   Friday before DST ({fri_spring.strftime('%Y-%m-%d')}): {fri_spring} (EST, 21:00 UTC)")
    print(f"   Monday after DST  ({mon_spring.strftime('%Y-%m-%d')}): {mon_spring} (EDT, 20:00 UTC)")
    assert fri_spring.hour == 21 and mon_spring.hour == 20
    results["spring_dst_transition"] = {"before_utc": str(fri_spring), "after_utc": str(mon_spring)}

    # 4. US Autumn Daylight-Saving Transition (November 2021)
    # DST transition occurred Sunday, November 7, 2021
    # Friday before DST ends: 2021-11-05 (EDT, UTC-4)
    # Monday after DST ends:  2021-11-08 (EST, UTC-5)
    fri_autumn = get_market_close_utc("2021-11-05")
    mon_autumn = get_market_close_utc("2021-11-08")
    print(f"4. US Autumn DST Transition (November 2021):")
    print(f"   Friday before DST ends ({fri_autumn.strftime('%Y-%m-%d')}): {fri_autumn} (EDT, 20:00 UTC)")
    print(f"   Monday after DST ends  ({mon_autumn.strftime('%Y-%m-%d')}): {mon_autumn} (EST, 21:00 UTC)")
    assert fri_autumn.hour == 20 and mon_autumn.hour == 21
    results["autumn_dst_transition"] = {"before_utc": str(fri_autumn), "after_utc": str(mon_autumn)}

    # 5. Filings before, exactly at, and after 16:00 ET cutoff
    # Evaluated on 2021-07-15 (EDT, 20:00:00 UTC close)
    session_d = "2021-07-15"
    ts_before = "2021-07-15 19:59:59+00:00"  # 1s before
    ts_exact  = "2021-07-15 20:00:00+00:00"  # Exactly at cutoff
    ts_after  = "2021-07-15 20:00:01+00:00"  # 1s after

    ok_before = is_record_eligible_for_trade(ts_before, session_d, session_d, "MARKET_CLOSE")
    ok_exact  = is_record_eligible_for_trade(ts_exact, session_d, session_d, "MARKET_CLOSE")
    ok_after  = is_record_eligible_for_trade(ts_after, session_d, session_d, "MARKET_CLOSE")

    print(f"5. Exact Cutoff Policy (Boundary Testing on {session_d} at 16:00:00 NY = 20:00:00 UTC):")
    print(f"   1s Before (19:59:59 UTC): {ok_before} (Expected: True)")
    print(f"   Exactly At (20:00:00 UTC): {ok_exact} (Expected: True - inclusive boundary)")
    print(f"   1s After  (20:00:01 UTC): {ok_after} (Expected: False - strictly excluded from session T)")
    assert ok_before is True and ok_exact is True and ok_after is False
    results["cutoff_boundary"] = {"before": ok_before, "exact": ok_exact, "after": ok_after}

    # 6. After-close filings becoming eligible next session
    next_session_d = "2021-07-16"
    ok_after_next = is_record_eligible_for_trade(ts_after, session_d, next_session_d, "MARKET_CLOSE")
    print(f"6. After-close filing eligibility on next session ({next_session_d}): {ok_after_next} (Expected: True)")
    assert ok_after_next is True

    # 7. Weekend and Holiday Filings
    # Weekend: Saturday 2021-05-15 accepted at 14:00 UTC
    sat_acc = "2021-05-15 14:00:00+00:00"
    ok_mon = is_record_eligible_for_trade(sat_acc, "2021-05-15", "2021-05-17", "MARKET_CLOSE")
    print(f"7a. Saturday filing eligible on Monday (2021-05-17): {ok_mon} (Expected: True)")
    assert ok_mon is True

    # Market Holiday: Memorial Day (Monday 2021-05-31). Filing on holiday accepted 15:00 UTC
    holiday_acc = "2021-05-31 15:00:00+00:00"
    ok_tues = is_record_eligible_for_trade(holiday_acc, "2021-05-31", "2021-06-01", "MARKET_CLOSE")
    print(f"7b. Holiday filing eligible on Tuesday (2021-06-01): {ok_tues} (Expected: True)")
    assert ok_tues is True

    # 8. Ambiguous / Missing Intraday Time (Midnight Fallback)
    midnight_acc = "2021-07-15 00:00:00+00:00"
    ok_same_day = is_record_eligible_for_trade(midnight_acc, "2021-07-15", "2021-07-15", "MARKET_CLOSE")
    ok_next_day = is_record_eligible_for_trade(midnight_acc, "2021-07-15", "2021-07-16", "MARKET_CLOSE")
    print(f"8. Midnight UTC fallback: Same-day eligible: {ok_same_day} (False) | Next-day eligible: {ok_next_day} (True)")
    assert ok_same_day is False and ok_next_day is True

    # 9. Restatements & Amendments Isolation
    mock_facts = pd.DataFrame([
        {"company_id": "C1", "cik": "1", "ticker": "T1", "concept": "Revenues", "label": "revenue",
         "period_end": "2020-12-31", "form": "10-K", "filed_date": "2021-02-15",
         "acceptance_timestamp": "2021-02-15 15:00:00+00:00", "accession_number": "1-21-1",
         "value": 1000.0, "unit": "USD", "source": "sec_edgar_companyfacts"},
        {"company_id": "C1", "cik": "1", "ticker": "T1", "concept": "Revenues", "label": "revenue",
         "period_end": "2020-12-31", "form": "10-K/A", "filed_date": "2021-08-15",
         "acceptance_timestamp": "2021-08-15 15:00:00+00:00", "accession_number": "1-21-2",
         "value": 800.0, "unit": "USD", "source": "sec_edgar_companyfacts"}
    ])
    engine = Phase8FinancialReportEngine(mock_facts)
    p_before = pd.DataFrame([{"company_id": "C1", "trading_date": "2021-05-01", "close": 10.0}])
    p_after  = pd.DataFrame([{"company_id": "C1", "trading_date": "2021-09-01", "close": 10.0}])
    f_before = engine.extract_point_in_time_features_for_panel(p_before)
    f_after  = engine.extract_point_in_time_features_for_panel(p_after)
    print(f"9. Restatement Isolation: is_amended before = {f_before.iloc[0]['fin_is_amended']} (0) | is_amended after = {f_after.iloc[0]['fin_is_amended']} (1)")
    assert f_before.iloc[0]["fin_is_amended"] == 0 and f_after.iloc[0]["fin_is_amended"] == 1

    print("\nAll 9 Temporal Integrity & DST tests passed successfully!")
    return results


def run_portfolio_audit_b() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("AUDIT B: PORTFOLIO & TRANSACTION-COST ARITHMETIC VERIFICATION")
    print("=" * 80)
    audit_b_results = {}

    df_holdout = pd.read_parquet(HOLDOUT_PREDS_PATH)
    models = {
        "pred_m_market_only": "Market Baseline (Frozen M4)",
        "pred_m_financial_specialist": "Financial Specialist (Model 3)",
        "pred_m_combined": "Combined Model (Market + Financials)",
    }

    dates = sorted(df_holdout["trading_date"].unique().tolist())
    all_cids = sorted(df_holdout["company_id"].unique().tolist())
    print(f"Holdout evaluated sessions: {len(dates)} | Unique cohort assets: {len(all_cids)}")

    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        saved_exp = json.load(f)

    for m_col, m_name in models.items():
        print(f"\n--- Model: {m_name} ({m_col}) ---")
        daily_gross_returns = []
        portfolio_weights = {}

        # 1. Trace daily quintile formation and dollar neutrality
        for d in dates:
            sub = df_holdout[df_holdout["trading_date"] == d].copy()
            if len(sub) >= 20:
                sub["rank"] = sub[m_col].rank(pct=True)
                long_leg = sub[sub["rank"] >= 0.80]
                short_leg = sub[sub["rank"] <= 0.20]

                n_l = len(long_leg)
                n_s = len(short_leg)

                # Weight vector: +1/n_l for long, -1/n_s for short
                w = {cid: 0.0 for cid in all_cids}
                for cid in long_leg["company_id"]:
                    w[cid] = 1.0 / n_l
                for cid in short_leg["company_id"]:
                    w[cid] = -1.0 / n_s

                # Verify dollar neutrality
                net_exp = sum(w.values())
                gross_exp = sum(abs(v) for v in w.values())
                assert np.isclose(net_exp, 0.0, atol=1e-10), f"Dollar neutrality violated on {d}: net={net_exp}"
                assert np.isclose(gross_exp, 2.0, atol=1e-10), f"Gross exposure mismatch on {d}: gross={gross_exp}"

                portfolio_weights[d] = w

                # 5-day holding return of the long-short spread: R_L - R_S
                r_l = long_leg["target_raw"].mean()
                r_s = short_leg["target_raw"].mean()
                ls_spread_5d = r_l - r_s

                # Staggered 5-tranche portfolio: effective 1-day step is spread / 5.0
                daily_gross_returns.append(ls_spread_5d / 5.0)

        # 2. Compute Empirical Day-over-Day Turnover
        one_way_turnover_series = []
        two_way_turnover_series = []
        for i in range(1, len(dates)):
            w_prev = portfolio_weights[dates[i - 1]]
            w_curr = portfolio_weights[dates[i]]
            delta_sum = sum(abs(w_curr[cid] - w_prev[cid]) for cid in all_cids)
            one_way_turnover_series.append(0.5 * delta_sum)
            two_way_turnover_series.append(delta_sum)

        emp_mean_one_way = float(np.mean(one_way_turnover_series))
        emp_mean_two_way = float(np.mean(two_way_turnover_series))

        # 3. Gross Return and Sharpe
        gross_arr = np.array(daily_gross_returns)
        T = len(gross_arr)
        cum_gross = float(np.prod(1.0 + gross_arr) - 1.0)
        ann_gross_ret = float(np.mean(gross_arr) * 252.0)
        ann_vol = float(np.std(gross_arr, ddof=1) * np.sqrt(252.0))
        gross_sharpe = float(ann_gross_ret / ann_vol)

        wealth = np.cumprod(1.0 + gross_arr)
        peaks = np.maximum.accumulate(wealth)
        max_dd = float(np.min((wealth - peaks) / peaks))

        print(f"  Gross Return: {cum_gross*100:+.2f}% | Ann Gross: {ann_gross_ret*100:+.2f}% | Ann Vol: {ann_vol*100:.2f}% | Sharpe: {gross_sharpe:+.2f} | Max DD: {max_dd*100:.2f}%")
        print(f"  Empirical Daily One-Way Turnover: {emp_mean_one_way*100:.2f}% | Two-Way Turnover: {emp_mean_two_way*100:.2f}%")

        # 4. Transaction Cost Deduction Verification
        # Documented definition:
        # Round-trip cost rate = (bps / 10000.0) * daily_turnover
        # Under the standardized staggered protocol assumption (daily_turnover = 0.40):
        # 10 bps: 0.0004 daily (10.08% annualized drag)
        # 20 bps: 0.0008 daily (20.16% annualized drag)
        # 30 bps: 0.0012 daily (30.24% annualized drag)
        scen_40 = {}
        for bps in [10, 20, 30]:
            cost_rate = (bps / 10000.0) * 0.40
            net_arr = gross_arr - cost_rate
            cum_net = float(np.prod(1.0 + net_arr) - 1.0)
            ann_net = float(np.mean(net_arr) * 252.0)
            sharpe_net = float(ann_net / ann_vol)
            scen_40[f"{bps}bps"] = {
                "cum_net_return": cum_net,
                "ann_net_return": ann_net,
                "net_sharpe": sharpe_net,
            }
            print(f"    Net Return @ {bps}bps (0.40 turnover): {cum_net*100:+.1f}% | Net Sharpe: {sharpe_net:+.2f}")

        # Sensitivity Analysis: Empirical Turnover
        scen_emp = {}
        for bps in [10, 20, 30]:
            cost_rate_emp = (bps / 10000.0) * emp_mean_one_way
            net_arr_emp = gross_arr - cost_rate_emp
            cum_net_emp = float(np.prod(1.0 + net_arr_emp) - 1.0)
            ann_net_emp = float(np.mean(net_arr_emp) * 252.0)
            sharpe_net_emp = float(ann_net_emp / ann_vol)
            scen_emp[f"{bps}bps"] = {
                "cum_net_return": cum_net_emp,
                "ann_net_return": ann_net_emp,
                "net_sharpe": sharpe_net_emp,
            }
            print(f"    Net Return @ {bps}bps (Empirical {emp_mean_one_way*100:.1f}% turnover): {cum_net_emp*100:+.1f}% | Net Sharpe: {sharpe_net_emp:+.2f}")

        # Verification against saved experiment results
        m_key = "m_market_only" if "market" in m_col else ("m_financial_specialist" if "financial" in m_col else "m_combined")
        saved_econ = saved_exp["holdout_results"][m_key]["economic_sim"]

        assert np.isclose(cum_gross, saved_econ["cum_gross_return"], atol=1e-5), f"Gross return mismatch: {cum_gross} vs {saved_econ['cum_gross_return']}"
        assert np.isclose(gross_sharpe, saved_econ["gross_sharpe"], atol=1e-5), f"Gross Sharpe mismatch: {gross_sharpe} vs {saved_econ['gross_sharpe']}"
        assert np.isclose(max_dd, saved_econ["max_drawdown"], atol=1e-5), f"Max DD mismatch: {max_dd} vs {saved_econ['max_drawdown']}"

        for bps in [10, 20, 30]:
            saved_net = saved_econ["cost_scenarios"][f"{bps}bps"]["cum_net_return"]
            assert np.isclose(scen_40[f"{bps}bps"]["cum_net_return"], saved_net, atol=1e-5), f"Net return mismatch at {bps}bps"

        audit_b_results[m_key] = {
            "name": m_name,
            "cum_gross_return": cum_gross,
            "ann_gross_return": ann_gross_ret,
            "ann_volatility": ann_vol,
            "gross_sharpe": gross_sharpe,
            "max_drawdown": max_dd,
            "standardized_turnover": 0.40,
            "empirical_one_way_turnover": emp_mean_one_way,
            "empirical_two_way_turnover": emp_mean_two_way,
            "standardized_cost_scenarios": scen_40,
            "empirical_cost_scenarios": scen_emp,
        }

    summary_file = OUTPUT_DIR / "phase8r1_verification_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(audit_b_results, f, indent=2)
    print(f"\nSaved Phase 8R.1 verification summary to {summary_file.relative_to(PROJECT_ROOT)}")
    return audit_b_results


def run_phase8r1_audit():
    t0 = time.time()
    res_a = run_temporal_audit_a()
    res_b = run_portfolio_audit_b()
    print(f"\nPhase 8R.1 Verification Engine completed in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    run_phase8r1_audit()
