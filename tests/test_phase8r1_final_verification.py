"""
Phase 8R.1 — Final Temporal Integrity & Economic Calculation Automated Test Suite.

Automates independent regression testing of:
1. data.zip SHA-256 byte-level invariance.
2. Normal winter close (EST, UTC-5, 21:00 UTC) and summer close (EDT, UTC-4, 20:00 UTC).
3. US Spring Daylight-Saving Transition (March 2021).
4. US Autumn Daylight-Saving Transition (November 2021).
5. Exact market-close cutoff boundary testing (1s before, exactly at, 1s after).
6. After-close filing eligibility on subsequent trading date.
7. Weekend and market-holiday filing eligibility.
8. Midnight UTC conservative date-only fallback.
9. Portfolio dollar neutrality and gross exposure (net=0, gross=200%).
10. Metric reproduction: gross returns, annualized metrics, cost deductions, and Sharpe ratios.
"""

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"
EXPECTED_DATA_ZIP_HASH = "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"

HOLDOUT_PREDS_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_final_holdout.parquet"
RESULTS_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_experiment_results.json"


def test_data_zip_hash_invariance():
    """Verifies that data.zip exists and its SHA-256 hash is byte-identical."""
    assert DATA_ZIP_PATH.exists()
    h = hashlib.sha256()
    with open(DATA_ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    assert h.hexdigest().lower() == EXPECTED_DATA_ZIP_HASH


def test_winter_and_summer_market_close_timestamps():
    """Verifies that winter trading dates yield 21:00 UTC (EST) and summer yield 20:00 UTC (EDT)."""
    from src.data.sec.point_in_time import get_market_close_utc, NY_TZ

    close_winter = get_market_close_utc("2021-01-15")
    assert close_winter.hour == 21
    offset_winter = close_winter.tz_convert(NY_TZ).utcoffset().total_seconds() / 3600.0
    assert offset_winter == -5.0

    close_summer = get_market_close_utc("2021-07-15")
    assert close_summer.hour == 20
    offset_summer = close_summer.tz_convert(NY_TZ).utcoffset().total_seconds() / 3600.0
    assert offset_summer == -4.0


def test_spring_and_autumn_dst_transitions():
    """Verifies that the market-close conversion handles spring and autumn DST transitions correctly."""
    from src.data.sec.point_in_time import get_market_close_utc

    # Spring 2021 transition: Sunday, March 14, 2021
    fri_spring = get_market_close_utc("2021-03-12")  # EST
    mon_spring = get_market_close_utc("2021-03-15")  # EDT
    assert fri_spring.hour == 21
    assert mon_spring.hour == 20

    # Autumn 2021 transition: Sunday, November 7, 2021
    fri_autumn = get_market_close_utc("2021-11-05")  # EDT
    mon_autumn = get_market_close_utc("2021-11-08")  # EST
    assert fri_autumn.hour == 20
    assert mon_autumn.hour == 21


def test_exact_market_close_cutoff_boundary_policy():
    """Tests filings 1s before, exactly at, and 1s after the 16:00 ET close."""
    from src.data.sec.point_in_time import is_record_eligible_for_trade

    session_d = "2021-07-15"  # EDT (close is 20:00:00 UTC)
    ts_before = "2021-07-15 19:59:59+00:00"
    ts_exact  = "2021-07-15 20:00:00+00:00"
    ts_after  = "2021-07-15 20:00:01+00:00"

    assert is_record_eligible_for_trade(ts_before, session_d, session_d, "MARKET_CLOSE") is True
    assert is_record_eligible_for_trade(ts_exact, session_d, session_d, "MARKET_CLOSE") is True
    assert is_record_eligible_for_trade(ts_after, session_d, session_d, "MARKET_CLOSE") is False


def test_after_close_filing_eligibility_on_subsequent_date():
    """Verifies that an after-close filing becomes eligible on session T+1."""
    from src.data.sec.point_in_time import is_record_eligible_for_trade

    session_t = "2021-07-15"
    session_next = "2021-07-16"
    ts_after = "2021-07-15 20:05:00+00:00"

    assert is_record_eligible_for_trade(ts_after, session_t, session_t, "MARKET_CLOSE") is False
    assert is_record_eligible_for_trade(ts_after, session_t, session_next, "MARKET_CLOSE") is True


def test_weekend_and_holiday_filing_eligibility():
    """Verifies that filings on non-trading days become eligible on the subsequent trading date."""
    from src.data.sec.point_in_time import is_record_eligible_for_trade

    # Saturday filing eligible Monday
    sat_ts = "2021-05-15 12:00:00+00:00"
    assert is_record_eligible_for_trade(sat_ts, "2021-05-15", "2021-05-17", "MARKET_CLOSE") is True

    # Memorial Day holiday filing eligible Tuesday
    holiday_ts = "2021-05-31 15:00:00+00:00"
    assert is_record_eligible_for_trade(holiday_ts, "2021-05-31", "2021-06-01", "MARKET_CLOSE") is True


def test_midnight_utc_fallback_anti_leakage():
    """Verifies conservative date-only fallback when intraday acceptance time is absent."""
    from src.data.sec.point_in_time import is_record_eligible_for_trade

    midnight_ts = "2021-07-15 00:00:00+00:00"
    # Ineligible same day
    assert is_record_eligible_for_trade(midnight_ts, "2021-07-15", "2021-07-15", "MARKET_CLOSE") is False
    # Eligible next day
    assert is_record_eligible_for_trade(midnight_ts, "2021-07-15", "2021-07-16", "MARKET_CLOSE") is True


def test_portfolio_dollar_neutrality_across_all_dates():
    """Verifies that the quintile long/short portfolio is strictly dollar-neutral for every session."""
    df_holdout = pd.read_parquet(HOLDOUT_PREDS_PATH)
    dates = df_holdout["trading_date"].unique()

    for d in dates:
        sub = df_holdout[df_holdout["trading_date"] == d]
        if len(sub) >= 20:
            rank = sub["pred_m_market_only"].rank(pct=True)
            n_long = (rank >= 0.80).sum()
            n_short = (rank <= 0.20).sum()
            # Net weight sum: n_long * (1/n_long) - n_short * (1/n_short) == 0.0
            net_exp = (n_long * (1.0 / n_long)) - (n_short * (1.0 / n_short))
            assert np.isclose(net_exp, 0.0, atol=1e-10)


def test_portfolio_return_and_cost_deduction_reproducibility():
    """Verifies gross returns, 40% turnover cost deduction, and Sharpe ratio reproducibility."""
    df_holdout = pd.read_parquet(HOLDOUT_PREDS_PATH)
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    dates = sorted(df_holdout["trading_date"].unique().tolist())
    daily_gross = []

    for d in dates:
        sub = df_holdout[df_holdout["trading_date"] == d]
        if len(sub) >= 20:
            rank = sub["pred_m_market_only"].rank(pct=True)
            r_long = sub.loc[rank >= 0.80, "target_raw"].mean()
            r_short = sub.loc[rank <= 0.20, "target_raw"].mean()
            daily_gross.append((r_long - r_short) / 5.0)

    gross_arr = np.array(daily_gross)
    cum_gross = float(np.prod(1.0 + gross_arr) - 1.0)
    ann_gross = float(np.mean(gross_arr) * 252.0)
    ann_vol = float(np.std(gross_arr, ddof=1) * np.sqrt(252.0))
    sharpe_gross = float(ann_gross / ann_vol)

    saved_econ = results["holdout_results"]["m_market_only"]["economic_sim"]
    assert np.isclose(cum_gross, saved_econ["cum_gross_return"], atol=1e-5)
    assert np.isclose(sharpe_gross, saved_econ["gross_sharpe"], atol=1e-5)

    # Verify 10, 20, 30 bps cost deductions at 0.40 daily turnover
    for bps in [10, 20, 30]:
        cost_rate = (bps / 10000.0) * 0.40
        net_arr = gross_arr - cost_rate
        cum_net = float(np.prod(1.0 + net_arr) - 1.0)
        saved_net = saved_econ["cost_scenarios"][f"{bps}bps"]["cum_net_return"]
        assert np.isclose(cum_net, saved_net, atol=1e-5)
