# PHASE 7A — FEATURE RE-ENGINEERING & STATIONARITY REPORT

**Lead Data Engineer & Quantitative Feature Architect**: AI-Powered Financial Intelligence Agent Architecture Team  
**Evaluation Date**: October 2026  
**Phase**: Phase 7A (Target Re-Engineering & Cross-Sectional Signal Research)  
**Derived Artifacts**: [`data/processed/research/phase7a/phase7a_predictions_oos.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase7a/phase7a_predictions_oos.parquet), [`data/processed/research/phase7a/phase7a_experiment_results.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase7a/phase7a_experiment_results.json)  

---

## 1. Executive Summary

Phase 6.9E demonstrated that the original feature space suffered from:
1. Exact duplicate columns (`market_momentum_5d/21d` identical to `market_return_5d/21d`).
2. High multicollinearity (`market_log_return_1d` vs `market_return_1d`, $r=0.993$).
3. Zero-variance deadweight (`fundamental_all_facts_stale` = `False` for 100% of rows).
4. Non-stationary nominal dollar share prices (`market_sma_20d/50d` ranging from $3.65 to $2,437.74).
5. Unscaled nominal per-share quantities (`fundamental_diluted_eps` ranging from -$375 to +$111).

In Phase 7A, we engineered a clean, stationary, economically interpretable feature architecture that restores cross-sectional comparability without sacrificing point-in-time safety.

---

## 2. Re-Engineered Feature Specifications

### 2.1 Cleaned Market Technical Feature Set (15 Features)

| Feature Name | Econometric Definition | Transformation / Formula | Purpose & Remediation |
| :--- | :--- | :--- | :--- |
| `market_return_1d` | 1-session return | $(P_T / P_{T-1}) - 1$ | Short-term momentum / mean reversion |
| `market_return_5d` | 5-session return | $(P_T / P_{T-5}) - 1$ | Weekly momentum; retained over duplicate |
| `market_return_21d` | 21-session return | $(P_T / P_{T-21}) - 1$ | Monthly momentum; retained over duplicate |
| `market_volatility_5d` | 5-day realized volatility | Rolling std dev of 1-day returns $\times \sqrt{252}$ | Short-term idiosyncratic risk |
| `market_volatility_21d`| 21-day realized volatility | Rolling std dev of 1-day returns $\times \sqrt{252}$ | Medium-term volatility regime |
| `market_volatility_63d`| 63-day realized volatility | Rolling std dev of 1-day returns $\times \sqrt{252}$ | Persistent volatility anchor |
| `market_momentum_63d` | 3-month momentum | $(P_T / P_{T-63}) - 1$ | Medium-term trend following |
| `market_distance_sma20`| Normalized distance to 20 SMA | $(P_T / \text{SMA}_{20,T}) - 1$ | **Replaces nominal SMA 20**; dimensionless ratio |
| `market_distance_sma50`| Normalized distance to 50 SMA | $(P_T / \text{SMA}_{50,T}) - 1$ | **Replaces nominal SMA 50**; dimensionless ratio |
| `market_sma_ratio` | Moving average convergence | $(\text{SMA}_{20,T} / \text{SMA}_{50,T}) - 1$ | Trend slope; eliminates collinearity |
| `market_zscore_20d` | Price z-score relative to 20 SMA | $(P_T - \text{SMA}_{20,T}) / \sigma_{20,T}$ | Bounded technical stretch [-4.5, +4.5] |
| `market_zscore_50d` | Price z-score relative to 50 SMA | $(P_T - \text{SMA}_{50,T}) / \sigma_{50,T}$ | Bounded technical stretch [-7.0, +7.0] |
| `market_rsi_14d` | Relative Strength Index | 14-session Wilder RSI $\in [0, 100]$ | Bounded oscillator |
| `market_volume_change_1d`| Volume surge ratio | $(V_T / V_{T-1}) - 1$ | Short-term liquidity shock |
| `market_volume_ratio_20d`| Volume relative to 20d median | $V_T / \text{Median}(V_{T-20 \to T})$ | Stationary volume activity |

**Features Removed from Original Market Matrix**:
1. `market_momentum_5d`: Dropped (exact duplicate of `market_return_5d`).
2. `market_momentum_21d`: Dropped (exact duplicate of `market_return_21d`).
3. `market_log_return_1d`: Dropped (multicollinear with arithmetic return, $r=0.9930$).
4. `market_sma_20d`: Dropped as raw nominal price ($3.65 to $2,437.74).
5. `market_sma_50d`: Dropped as raw nominal price ($4.46 to $2,307.80).

---

### 2.2 Validated Fundamental Accounting Feature Set (7 Features)

To enable cross-sectional comparability, accounting metrics were normalized by market price or balance sheet size and clipped to prevent extreme denominator distortion:

| Feature Name | Econometric Definition | Formula & Boundaries | Treatment of Outliers / Denominators |
| :--- | :--- | :--- | :--- |
| `fundamental_earnings_yield` | Earnings Yield ($E/P$) | $\text{clip}(\text{EPS}_T / P_T, \, -0.5, \, 0.5)$ | **Replaces raw per-share EPS**. Stable valuation metric; avoids P/E singularity at $E \to 0$. |
| `fundamental_net_margin_cl` | Net Profit Margin | $\text{clip}(\text{Net Income} / \text{Revenue}, \, -2.0, \, 2.0)$ | Winsorized; prevents extreme ratios in micro-revenue firms. |
| `fundamental_roa_cl` | Return on Assets | $\text{clip}(\text{Net Income} / \text{Total Assets}, \, -1.0, \, 1.0)$ | Bounded asset efficiency metric. |
| `fundamental_debt_to_assets_cl`| Leverage Ratio | $\text{clip}(\text{Total Debt} / \text{Total Assets}, \, 0.0, \, 5.0)$ | Positive leverage measure; bounded right tail. |
| `fundamental_debt_to_equity_cl`| Financial Gearing | $\text{clip}(\text{Total Debt} / \text{Equity}, \, -5.0, \, 10.0)$ | Explicitly bounds negative equity in buyback/distressed firms. |
| `fundamental_ocf_to_ni_cl` | Cash Flow Quality | $\text{clip}(\text{OCF} / \text{Net Income}, \, -10.0, \, 10.0)$ | Accruals proxy; avoids explosion when Net Income $\approx 0$. |
| `fundamental_revenue_age_days`| Statement Freshness | Calendar days since filing $\in [1, 258]$ | Captures staggered quarterly reporting cadence. |

**Features Removed from Original Fundamental Matrix**:
1. `fundamental_all_facts_stale`: Dropped (100% constant `False`, zero variance).
2. `fundamental_diluted_eps`: Dropped as raw nominal per-share quantity (-$375.88 to +$111.82).

---

## 3. Summary of Feature Sets Used in Model Matrix

| Feature Set Identifier | Modalities Included | Count | Stationarity Status | Cross-Company Comparable? |
| :--- | :--- | :---: | :---: | :---: |
| **Set 1: Original Market Features** | Raw Market Baseline | 17 | Impaired by nominal SMAs | No (Price-level biased) |
| **Set 2: Cleaned Market Features** | Stationary Technical Features | 15 | Fully stationary ratios | **Yes** |
| **Set 3: Cleaned Multimodal Features**| Cleaned Market + Validated Fundamentals | 22 | Fully stationary & bounded | **Yes** |

All feature imputation and scaling operations were fitted exclusively on training folds, preserving temporal isolation across all 54,900 out-of-sample observations.
