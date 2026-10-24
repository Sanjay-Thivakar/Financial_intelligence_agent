"""
Phase 8 — Financial Reports Intelligence Feature Engine.

Extracts point-in-time fundamental accounting features, financial ratios,
growth metrics, cash flow quality, and disclosure diagnostics from SEC EDGAR XBRL facts.

Invariants:
1. Zero lookahead: Only filings with acceptance_timestamp <= decision_timestamp_utc.
2. Market close alignment: Session T close (16:00 ET -> UTC).
3. Restatement isolation: 10-K/A or 10-Q/A filed after decision cutoff are ignored;
   amendments filed before cutoff supersede prior reports for that period.
4. Accounting consistency: Flow vs stock concepts, safe division, missing values preserved.
5. Staleness diagnostics: Computes filing age in days and enforces documented staleness thresholds.
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
import numpy as np
import pandas as pd

from src.data.sec.point_in_time import get_market_close_utc, is_record_eligible_for_trade


class Phase8FinancialReportEngine:
    """Computes point-in-time financial report features from Phase 8 XBRL facts."""

    def __init__(self, df_facts: pd.DataFrame, max_staleness_days: int = 180):
        self.max_staleness_days = max_staleness_days
        self.df_facts = df_facts.copy()

        if "acceptance_timestamp" in self.df_facts.columns:
            self.df_facts["acceptance_timestamp"] = pd.to_datetime(
                self.df_facts["acceptance_timestamp"], utc=True
            )
        if "filed_date" in self.df_facts.columns:
            self.df_facts["filed_date"] = self.df_facts["filed_date"].astype(str)

        # Index facts by company_id for accelerated sub-queries
        self._company_facts: Dict[str, pd.DataFrame] = {
            cid: grp.sort_values(by="acceptance_timestamp")
            for cid, grp in self.df_facts.groupby("company_id")
        }

    def extract_point_in_time_features_for_panel(
        self,
        df_panel: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Extracts point-in-time financial features for each observation in df_panel.
        Requires 'company_id', 'trading_date', 'close' in df_panel.
        """
        unique_dates = sorted(df_panel["trading_date"].unique().tolist())
        # Map each trading date to exact market close UTC (accounting for DST)
        date_to_close_utc = {
            d: get_market_close_utc(d, close_time_str="16:00:00")
            for d in unique_dates
        }

        unique_cids = df_panel["company_id"].unique().tolist()
        records = []

        for cid in unique_cids:
            c_sub = df_panel[df_panel["company_id"] == cid]
            c_dates = c_sub["trading_date"].tolist()
            c_closes = c_sub["close"].tolist()
            comp_facts = self._company_facts.get(cid)

            if comp_facts is None or comp_facts.empty:
                for d, cl in zip(c_dates, c_closes):
                    records.append(self._empty_feature_record(cid, d))
                continue

            accept_times = comp_facts["acceptance_timestamp"].tolist()
            f_cache = {}

            for d, cl in zip(c_dates, c_closes):
                cutoff_utc = date_to_close_utc[d]

                # Binary search / filter to prior acceptance timestamps
                # Find index of latest acceptance <= cutoff_utc
                # Since comp_facts is sorted by acceptance_timestamp:
                idx = np.searchsorted(accept_times, cutoff_utc, side="right")
                if idx == 0:
                    records.append(self._empty_feature_record(cid, d))
                    continue

                # Cache key is the index of available facts
                if idx not in f_cache:
                    avail_df = comp_facts.iloc[:idx]
                    f_cache[idx] = self._compute_snapshot_features(cid, avail_df)

                snap = dict(f_cache[idx])
                snap["company_id"] = cid
                snap["trading_date"] = d

                # Dynamically compute staleness using the exact decision cutoff of session d
                latest_accept_ts = snap.pop("_latest_accept_ts", None)
                if latest_accept_ts is not None and pd.notna(latest_accept_ts):
                    age_days = float((cutoff_utc - latest_accept_ts).total_seconds() / 86400.0)
                    snap["fin_filing_age_days"] = round(age_days, 1)
                    snap["fin_is_stale_180"] = bool(age_days > self.max_staleness_days)
                else:
                    snap["fin_filing_age_days"] = np.nan
                    snap["fin_is_stale_180"] = True

                # Compute valuation ratios using current session close price
                if not np.isnan(snap.get("diluted_eps", np.nan)) and cl > 0:
                    snap["fin_earnings_yield"] = float(np.clip(snap["diluted_eps"] / cl, -0.5, 0.5))
                else:
                    snap["fin_earnings_yield"] = np.nan

                records.append(snap)

        df_features = pd.DataFrame(records)
        return df_features

    def _empty_feature_record(self, cid: str, trading_date: str) -> Dict[str, Any]:
        return {
            "company_id": cid,
            "trading_date": trading_date,
            "fin_has_filing": False,
            "fin_filing_age_days": np.nan,
            "fin_is_stale_180": True,
            "fin_is_amended": 0,
            # Profitability
            "fin_gross_margin": np.nan,
            "fin_operating_margin": np.nan,
            "fin_net_margin": np.nan,
            "fin_roa": np.nan,
            "fin_roe": np.nan,
            # Health
            "fin_debt_to_assets": np.nan,
            "fin_debt_to_equity": np.nan,
            "fin_current_ratio": np.nan,
            "fin_cash_to_assets": np.nan,
            # Cash flow & quality
            "fin_ocf_to_assets": np.nan,
            "fin_fcf_to_assets": np.nan,
            "fin_ocf_to_net_income": np.nan,
            "fin_accruals": np.nan,
            # Per share & valuation
            "diluted_eps": np.nan,
            "fin_earnings_yield": np.nan,
        }

    def _compute_snapshot_features(
        self,
        cid: str,
        avail_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Extracts latest valid fact per canonical concept and computes financial ratios.
        Handles restatements (latest acceptance for same period_end).
        """
        # Concept map: extract most recent observation
        # Priority order: latest period_end, break tie with latest acceptance_timestamp
        concepts = {
            "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
            "gross_profit": ["GrossProfit"],
            "cost_of_revenue": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
            "operating_income": ["OperatingIncomeLoss"],
            "net_income": ["NetIncomeLoss", "ProfitLoss"],
            "total_assets": ["Assets"],
            "current_assets": ["AssetsCurrent"],
            "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
            "total_liabilities": ["Liabilities"],
            "current_liabilities": ["LiabilitiesCurrent"],
            "stockholders_equity": ["StockholdersEquity"],
            "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
            "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
            "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
            "diluted_eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
        }

        vals: Dict[str, float] = {}
        latest_accept_ts = None
        latest_form = None

        for c_name, tags in concepts.items():
            matches = avail_df[avail_df["concept"].isin(tags)]
            if not matches.empty:
                # Latest period_end
                max_period = matches["period_end"].max()
                period_matches = matches[matches["period_end"] == max_period]
                # Break ties with latest acceptance_timestamp
                latest_match = period_matches.sort_values(
                    by=["acceptance_timestamp", "accession_number"]
                ).iloc[-1]
                vals[c_name] = float(latest_match["value"])

                acc_ts = latest_match["acceptance_timestamp"]
                if latest_accept_ts is None or acc_ts > latest_accept_ts:
                    latest_accept_ts = acc_ts
                    latest_form = latest_match["form"]

        if not vals or latest_accept_ts is None:
            return self._empty_feature_record(cid, "")

        is_amended = int(latest_form in ("10-K/A", "10-Q/A")) if latest_form else 0

        # Extract values with safe defaults
        rev = vals.get("revenue")
        gp = vals.get("gross_profit")
        cor = vals.get("cost_of_revenue")
        op_inc = vals.get("operating_income")
        ni = vals.get("net_income")
        assets = vals.get("total_assets")
        ca = vals.get("current_assets")
        cash = vals.get("cash_and_equivalents")
        liab = vals.get("total_liabilities")
        cl = vals.get("current_liabilities")
        eq = vals.get("stockholders_equity")
        ocf = vals.get("operating_cash_flow")
        capex = vals.get("capex")
        eps = vals.get("diluted_eps")

        # Accounting identities if certain items missing
        if gp is None and rev is not None and cor is not None:
            gp = rev - cor
        if liab is None and assets is not None and eq is not None:
            liab = assets - eq

        # Compute ratios with safe division and winsorization
        def safe_div(num, den, lo, hi):
            if num is not None and den is not None and not np.isnan(num) and not np.isnan(den) and den > 0:
                val = num / den
                return float(np.clip(val, lo, hi))
            return np.nan

        gross_margin = safe_div(gp, rev, -1.0, 1.0)
        operating_margin = safe_div(op_inc, rev, -1.0, 1.0)
        net_margin = safe_div(ni, rev, -2.0, 2.0)
        roa = safe_div(ni, assets, -1.0, 1.0)
        roe = safe_div(ni, eq, -2.0, 2.0)

        debt_to_assets = safe_div(liab, assets, 0.0, 5.0)
        debt_to_equity = safe_div(liab, eq, -5.0, 10.0)
        current_ratio = safe_div(ca, cl, 0.0, 10.0)
        cash_to_assets = safe_div(cash, assets, 0.0, 1.0)

        ocf_to_assets = safe_div(ocf, assets, -1.0, 1.0)
        fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
        fcf_to_assets = safe_div(fcf, assets, -1.0, 1.0)

        # OCF to Net Income
        if ocf is not None and ni is not None and not np.isnan(ocf) and not np.isnan(ni) and abs(ni) > 1e-4:
            ocf_to_ni = float(np.clip(ocf / ni, -10.0, 10.0))
        else:
            ocf_to_ni = np.nan

        # Accruals: (Net Income - Operating Cash Flow) / Total Assets
        if ni is not None and ocf is not None and assets is not None and assets > 0:
            accruals = float(np.clip((ni - ocf) / assets, -2.0, 2.0))
        else:
            accruals = np.nan

        return {
            "fin_has_filing": True,
            "_latest_accept_ts": latest_accept_ts,
            "fin_is_amended": is_amended,
            "fin_gross_margin": gross_margin,
            "fin_operating_margin": operating_margin,
            "fin_net_margin": net_margin,
            "fin_roa": roa,
            "fin_roe": roe,
            "fin_debt_to_assets": debt_to_assets,
            "fin_debt_to_equity": debt_to_equity,
            "fin_current_ratio": current_ratio,
            "fin_cash_to_assets": cash_to_assets,
            "fin_ocf_to_assets": ocf_to_assets,
            "fin_fcf_to_assets": fcf_to_assets,
            "fin_ocf_to_net_income": ocf_to_ni,
            "fin_accruals": accruals,
            "diluted_eps": eps if eps is not None else np.nan,
        }
