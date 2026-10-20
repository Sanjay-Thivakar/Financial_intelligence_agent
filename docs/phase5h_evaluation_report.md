# Phase 5H — Portfolio Simulation & Leakage-Safe Threshold Validation Report

**Phase**: 5H  
**Component**: Portfolio Simulation & Rolling Threshold Validation  
**Status**: Experimental Research Report  
**Date**: October 2026  
**Disclaimer**: This report evaluates a research portfolio-simulation and risk-accounting framework. Realized historical returns under hypothetical execution models do **not** constitute realized trading profits, investment advice, or guaranteed future performance.

---

## 1. Executive Summary

Phase 5H implements a **Deterministic Portfolio Simulator** and a **Leakage-Safe Rolling Chronological Threshold Selector** to evaluate the Phase 5G Decision & Risk Layer under institutional portfolio constraints across the audited 4-fold walk-forward panel ($N = 720$ observations across `AAPL`, `JPM`, `GOOG`, `TSLA`).

### Key Empirical Findings:

1. **Resolution of Overlapping Positions & Capital Commitments**:
   - In Phase 5G, 7 candidate `BUY` signals were generated in `AAPL` during Fold 3 and evaluated as independent trades.
   - Under realistic portfolio constraints with `allow_multiple_positions_per_ticker = False` (preventing stacking overlapping positions in the exact same equity):
     - **2 independent non-overlapping trades** were funded and executed.
     - **5 overlapping signals were rejected** with `MAX_TICKER_EXPOSURE` to protect the portfolio from extreme single-asset concentration.
   - On the 2 funded trades, the portfolio grew from $\$100,000.00$ to **$\$100,133.46$ (+0.13% net portfolio return)**, with a maximum drawdown of only **-0.73%** and total transaction friction of **$\$75.13$**.

2. **Empirical Validation of Rolling Threshold Selection (Leakage-Safe Protocol)**:
   - **Folds 0 and 1**: Inner validation correctly identified sparse trading opportunities ($< 3$ trades clearing hurdles). The **conservative fallback threshold ($1.5\%$)** triggered automatically, preserving capital 100% in cash.
   - **Fold 2 (COVID Crash)**: Inner validation on late-2019 data selected a looser threshold ($\theta^* = 0.5\%$). When applied out-of-sample to Fold 2 (February–March 2020), this loose threshold admitted 13 BUY orders during the crash, producing an overall strategy net return of **-4.18%** and a **-4.90% drawdown**.
   - **Fold 3 (Liquidity Rebound)**: Inner validation selected $\theta^* = 1.0\%$, admitting 14 BUY orders.
   - **Critical Scientific Takeaway**: This finding definitively confirms that the exploratory $1.0\% - 1.5\%$ "sweet spot" identified post-hoc in Phase 5G suffered from look-ahead selection bias. A rolling selector tuned on pre-crash data lowered thresholds, exposing the portfolio to regime transitions.

3. **Comparison Against Benchmarks**:
   - **Cash Benchmark**: Return = $0.00\%$, Max Drawdown = $0.00\%$, Volatility = $0.00\%$.
   - **Equal-Weight Buy & Hold (4 Equities)**: Final Equity = **$\$208,738.51$ (+108.74% return)**, but experienced a catastrophic **-40.82% maximum drawdown** during the March 2020 crash and high annualized volatility of **36.83%**.
   - **Fixed Policy (1.5% Threshold)**: Preserved capital defensively during the crash (0.00% drawdown in Folds 0–2), capturing $+0.13\%$ portfolio return in Fold 3 with minimal volatility ($0.71\%$) and low drawdown ($-0.73\%$).

---

## 2. Evaluation Methodology & Walk-Forward Setup

### 2.1 Panel & Temporal Structure
- **Cohort**: 4 verified companies (`AAPL`, `JPM`, `GOOG`, `TSLA`). Excluded ticker `AA` remained strictly barred.
- **Evaluation Period**: 2019-01-01 through 2020-06-10 (358 unique calendar dates, 1,432 labeled panel rows).
- **Folds**: 4 chronological expanding walk-forward folds identical to Phase 5F/5G ($N = 180 \times 4 = 720$ out-of-sample observations).

### 2.2 Portfolio Simulation Configuration
- Initial Capital: $\$100,000.00$
- Maximum Concurrent Positions: $4$
- Target Allocation per Trade: $25\%$ ($\$25,000.00$ maximum per position)
- Maximum Aggregate Exposure: $100\%$ ($1.0$, zero leverage)
- Holding Horizon: $5$ trading sessions (entry at $T+1$ open, exit at $T+5$ close)
- Transaction Friction: $15.0\text{ bps}$ base round-trip ($2.5\text{ bps}$ entry, $2.5\text{ bps}$ exit, $5.0\text{ bps}$ spread, $5.0\text{ bps}$ slippage)
- Position Stacking: Disallowed (`allow_multiple_positions_per_ticker = False`)

---

## 3. Rolling Threshold Selection Results by Fold

Inner chronological validation was executed strictly on historical data prior to each outer fold ($V_{\text{inner}} = 45$ sessions, $P_{\text{inner}} = 5$ purge sessions):

| Outer Fold | Outer Val Window | Prior Train Sessions | Selected Threshold ($\theta^*$) | Fallback Used | Diagnostic Selection Reason |
|---|---|---|---|---|---|
| **Fold 0** | 2019-09-17 $\to$ 2019-11-18 | 173 sessions | **1.5%** | **Yes** | Sparse inner evidence: No candidate threshold produced $\ge 3$ active trades with $\ge 50\%$ win rate. |
| **Fold 1** | 2019-11-19 $\to$ 2020-01-24 | 218 sessions | **1.5%** | **Yes** | Sparse inner evidence: No candidate threshold produced $\ge 3$ active trades with $\ge 50\%$ win rate. |
| **Fold 2** | 2020-01-27 $\to$ 2020-03-30 | 263 sessions | **0.5%** | **No** | Optimized on Inner Val: Threshold 0.5% produced 4 trades with +1.28% mean net return. |
| **Fold 3** | 2020-03-31 $\to$ 2020-06-03 | 308 sessions | **1.0%** | **No** | Optimized on Inner Val: Threshold 1.0% produced 3 trades with +2.15% mean net return. |

---

## 4. Comprehensive Strategy Benchmark Comparison

All strategies were simulated across the identical calendar period and execution pricing:

| Performance Metric | Cash Benchmark | Equal-Weight Buy & Hold | Fixed Policy (1.5% Threshold) | Rolling Threshold Policy |
|---|---|---|---|---|
| **Initial Equity** | $\$100,000.00$ | $\$100,000.00$ | $\$100,000.00$ | $\$100,000.00$ |
| **Final Equity** | $\$100,000.00$ | **$\$208,738.51$** | **$\$100,133.46$** | **$\$95,821.25$** |
| **Total Cumulative Net Return** | 0.00% | **+108.74%** | **+0.13%** | **-4.18%** |
| **Annualized Net Return** | 0.00% | +66.68% | +0.09% | -2.92% |
| **Maximum Drawdown** | **0.00%** | **-40.82%** (COVID Crash) | **-0.73%** | **-4.90%** |
| **Annualized Daily Volatility** | 0.00% | 36.83% | **0.71%** | 2.48% |
| **Sharpe Ratio ($R_f = 0\%$)** | 0.00 | 1.57 | 0.13 | -1.18 |
| **Total Closed Trades Taken** | 0 | 4 | **2** | **8** |
| **Win Rate on Closed Trades** | N/A | 100.0% | **50.0%** | **37.5%** |
| **Mean Net Return per Trade** | N/A | +108.74% | **+0.27%** | **-2.09%** |
| **Total Transaction Friction** | $\$0.00$ | $\$231.73$ | **$\$75.13$** | **$\$291.07$** |
| **Total Rejected Orders** | 0 | 0 | **5** (`MAX_TICKER`) | **19** (`MAX_TICKER`) |
| **Average Capital Utilization** | 0.0% | 99.8% | **0.7%** | **2.8%** |
| **Maximum Capital Utilization** | 0.0% | 100.1% | **25.4%** | **50.5%** |

### Critical Comparison Analysis:
1. **Capital Allocation & Concentration Risk**:
   In Phase 5G, reporting 7 trades created the illusion that 7 independent positions could be funded. The portfolio simulator revealed that 5 of those 7 signals arrived while an existing `AAPL` position was still open, correctly triggering `MAX_TICKER_EXPOSURE` rejections and restricting actual market risk to $\$25,000$ (25% weight).
2. **Crash Resilience vs. Beta Exposure**:
   Buy & Hold achieved high cumulative return (+108.74%) due to the secular tech bull market (especially `TSLA`), but suffered a severe $-40.82\%$ drawdown. The Fixed Policy functioned as an absolute-return capital preservation strategy, achieving a tiny positive gain (+0.13%) with negligible drawdown (-0.73%).
3. **The Regime Shift Vulnerability of Rolling Optimization**:
   The Rolling Policy demonstrated the danger of parameter tuning across structural breaks: tuning on the calm late-2019 market led the optimizer to select $0.5\%$, which admitted losing trades right as the COVID crisis struck.

---

## 5. Stress Testing & Sensitivity Analysis

### 5.1 Transaction Cost Sensitivity (Base Weight = 25%, Max Concurrent = 4)
| Friction Level | Fixed Policy Net Return | Fixed Policy Friction Paid | Rolling Policy Net Return | Rolling Policy Friction Paid |
|---|---|---|---|---|
| **Low (5.0 bps)** | **+0.18%** | $\$25.05$ | **-3.99%** | $\$97.10$ |
| **Base (15.0 bps)** | **+0.13%** | $\$75.13$ | **-4.18%** | $\$291.07$ |
| **High (30.0 bps)** | **+0.06%** | $\$150.23$ | **-4.47%** | $\$581.51$ |

*Takeaway*: Across all scenarios, higher friction monotonically reduces net return and doubles total cost drag, but does not alter the fundamental defensive behavior of the fixed policy.

### 5.2 Position Sizing Weight Sensitivity (Base Cost = 15 bps, Max Concurrent = 4)
| Target Max Weight | Fixed Policy Net Return | Fixed Max Capital Utilization | Rolling Policy Net Return | Rolling Max Capital Utilization |
|---|---|---|---|---|
| **15% Weight** | +0.08% | 15.3% | -2.51% | 30.4% |
| **25% Weight (Base)** | +0.13% | 25.4% | -4.18% | 50.5% |
| **50% Weight** | +0.27% | 50.6% | -8.34% | 100.1% |

*Takeaway*: Higher position weights scale returns linearly with invested capital. At 50% allocation, Rolling Policy losses double to $-8.34\%$.

### 5.3 Concurrent Position Limit Sensitivity (Base Cost = 15 bps, Weight = 25%)
| Concurrent Position Cap | Fixed Policy Net Return | Fixed Rejections | Rolling Policy Net Return | Rolling Rejections |
|---|---|---|---|---|
| **2 Positions** | +0.13% | 5 | -4.18% | 19 |
| **4 Positions (Base)** | +0.13% | 5 | -4.18% | 19 |
| **8 Positions** | +0.13% | 5 | -4.18% | 19 |

*Takeaway*: Because candidate signals are concentrated exclusively in single tickers (`AAPL`) during short windows, expanding concurrent slots beyond 2 has no effect without allowing multiple positions in the same ticker.

---

## 6. Documented Limitations & Research Risks

1. **Signal Sparsity Remains Dominant**: The strategy behaves essentially as a cash repository with brief tactical allocations (average capital utilization $< 1.0\%$).
2. **Single-Ticker Concentration**: Almost all active signals cleared by risk gates occurred in `AAPL`. `JPM`, `GOOG`, and `TSLA` failed gates consistently due to high annualized volatility.
3. **Small Company Universe ($N = 4$)**: The findings reflect large-cap US tech/financial dynamics and cannot be extrapolated to small-cap or non-US equities.
4. **Unmodeled Short Selling**: SELL candidate signals remained unfunded because institutional short selling (borrow fees, locate availability, short squeeze risk) was excluded.

---

## 7. Deliverables Generated

1. `src/portfolio/schema.py`: Pydantic models for portfolio configuration, position lifecycle records, daily snapshots, and rolling threshold results.
2. `src/portfolio/simulator.py`: `DeterministicPortfolioSimulator` with exact mark-to-market accounting and capital reconciliation.
3. `src/portfolio/rolling.py`: `RollingThresholdSelector` implementing inner chronological cross-validation with conservative fallback.
4. `scripts/evaluate_phase5h.py`: Reproducible evaluation runner generating the machine-readable artifact `phase5h_portfolio_evaluation_results.json`.
5. `tests/test_portfolio_simulation.py`: 10 comprehensive unit and integration tests covering conservation of capital, rejection rules, and API endpoints.
6. `frontend/src/components/PredictionResearchTab.jsx`: Added Phase 5H Portfolio Simulation & Rolling Validation Card to the dashboard UI.
