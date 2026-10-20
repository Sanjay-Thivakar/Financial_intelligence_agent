# Phase 5K.1 — Targeted Benchmark and Portfolio Comparison Reconciliation

**Status:** COMPLETE & VERIFIED  
**Final Verdict:** ACCEPT WITH DOCUMENTED LIMITATIONS  
**Evaluation Date:** October 20, 2026  
**Auditor / Author:** Quantitative ML Research & Integrity Auditor  
**Scope:** Narrow audit of completed Phase 5K implementation, reconciling the Equal-Weight Buy-and-Hold benchmark disparity (+4.71% vs +5.72%), clarifying zero-trade portfolio results across learned and transformed models, and verifying full simulation accounting integrity.

---

## 1. Executive Summary & Verdict

This audit performs a targeted reconciliation of the Phase 5K model improvement evaluation without repeating full training cycles, modifying outer-fold schedules, altering risk gates, or tuning thresholds on out-of-sample data.

### Audit Summary
1. **Buy-and-Hold Benchmark Reconciled (+4.71% vs +5.72%):**
   The disparity between Phase 5J (+4.71%, \$104,709.12) and Phase 5K (+5.72%, \$105,724.86) has been identified down to machine precision. It is caused entirely by the terminal horizon parameter in the portfolio simulator:
   - **Phase 5J:** Evaluated across all **188 sessions** of the available market simulation series (`2019-09-17` to `2020-06-15`), closing positions on `2020-06-15` and absorbing the **June 11, 2020 macro pullback (-6.90% drop in S&P 500)**, resulting in **+4.71% net return**.
   - **Initial Phase 5K:** Evaluated across the **180 sessions** of the decision window (`2019-09-17` to `2020-06-03`), closing positions on `2020-06-04` before the June 11 pullback, resulting in **+5.72% net return**.
   Both figures are mathematically reproduced and correct for their respective terminal dates. For cross-phase continuity and honest benchmark comparison, `scripts/evaluate_phase5k.py` and `phase5k_model_experiment_results.json` have been reconciled to designate the 188-session full market window (+4.71%) as the primary benchmark while preserving the 180-session decision-window horizon (+5.72%) as a documented variant.

2. **Zero-Trade Portfolio Results Clarified:**
   The portfolio simulation for ElasticNet, HistGradientBoosting, Ridge CS Demeaned, and Ridge Sector Neutral generated zero trades under the fixed Phase 5G policy. Signal funnel diagnostics reveal:
   - **HistGradientBoosting** generated **235 candidate BUY signals** with gross forecasts $\ge +1.65\%$ (net expected returns $\ge +1.50\%$). However, **100% of these 235 candidate signals occurred during high market volatility sessions** ($\sigma_{\text{vol}} > 0.1500$, mean $1.07$, range $[0.1858, 2.3789]$) and were defensively intercepted by the Phase 5G Abnormal Volatility Gate.
   - **ElasticNet** produced **0 candidate BUY signals** $\ge +1.50\%$ because $L_1$ shrinkage capped maximum out-of-sample predictions at $+0.94\%$, falling below the $+1.50\%$ net return hurdle.
   - **Cross-Sectional Demeaned & Sector-Neutral** models produced candidate signals during high-volatility regimes that were likewise intercepted by the Volatility Gate.
   - For all zero-trade models, the simulator correctly preserved 100% of capital (\$100,000.00 cash, \$0.00 transaction costs, 0.00% max drawdown, 0.00% return). These results are explicitly labeled **"no positions executed under the fixed policy"** and reflect prudent defensive gating rather than portfolio execution failure.

3. **Research Integrity Preserved:**
   No models were retuned or re-optimized. HistGradientBoosting maintains a modest error reduction (RMSE 0.0644 vs 0.0652 for Ridge), but its daily cross-sectional Spearman rank IC remains statistically indistinguishable from zero (mean IC -0.0267, Newey-West HAC $p = 0.4512$).

**Verdict:** **ACCEPT WITH DOCUMENTED LIMITATIONS**

---

## 2. Reconcile the Buy-and-Hold Benchmark

### 2.1 Root Cause Analysis

In Phase 5J, the 60-company panel was simulated through a deterministic equal-weight buy-and-hold portfolio. The two evaluations differed solely in the integer assigned to `holding_horizon_sessions` in `PortfolioConfig`:

$$\text{Phase 5J: } \text{holding\_horizon\_sessions} = \text{len}(\text{sim\_dates}) = 188$$
$$\text{Phase 5K (Initial): } \text{holding\_horizon\_sessions} = \text{len}(\text{val\_dates\_all}) = 180$$

```
Market Simulation Window (188 Sessions):  2019-09-17 ------------------------------> 2020-06-15
Phase 5J Holding Horizon (188 Sessions):  [Entry: 2019-09-18 Open] -----------------> [Exit: 2020-06-15 Close] -> Net +4.71%
Phase 5K Decision Horizon (180 Sessions): [Entry: 2019-09-18 Open] ---------> [Exit: 2020-06-04 Close] ---------> Net +5.72%
                                                                                    ^
                                                                          June 11 Macro Pullback (-6.9%)
```

On **June 11, 2020**, the broader US market suffered a sharp macro correction due to COVID resurgence concerns (Dow dropped $-6.9\%$, S&P 500 dropped $-5.9\%$). 
- The **180-session horizon** closed on `2020-06-04`, liquidating prior to the June 11 pullback at near-peak recovery levels (\$105,724.86, +5.72%).
- The **188-session horizon** remained invested through `2020-06-15`, absorbing the June 11 shock before settling at \$104,709.12 (+4.71%).

### 2.2 Detailed Methodological Comparison

| Dimension | Phase 5J Buy & Hold | Phase 5K Buy & Hold (Initial) | Phase 5K.1 Reconciled Primary | Reconciliation Status |
| :--- | :--- | :--- | :--- | :--- |
| **Start Date (Entry)** | `2019-09-17` close $\to$ `2019-09-18` open | `2019-09-17` close $\to$ `2019-09-18` open | `2019-09-17` close $\to$ `2019-09-18` open | **Identical** |
| **End Date (Exit)** | `2020-06-15` close | `2020-06-04` close | `2020-06-15` close | **Reconciled** |
| **Number of Sessions** | 188 sessions | 180 sessions | 188 sessions | **Reconciled** |
| **Active Cohort** | 60 companies | 60 companies | 60 companies | **Identical** |
| **Eligible Initial Tickers** | 60 tickers | 60 tickers | 60 tickers | **Identical** |
| **Initial Capital** | \$100,000.00 | \$100,000.00 | \$100,000.00 | **Identical** |
| **Target Weighting** | Equal-weight ($1/60 \approx 1.667\%$) | Equal-weight ($1/60 \approx 1.667\%$) | Equal-weight ($1/60 \approx 1.667\%$) | **Identical** |
| **Rebalancing Policy** | Buy and hold (no rebalancing) | Buy and hold (no rebalancing) | Buy and hold (no rebalancing) | **Identical** |
| **Price Adjustment** | Tiingo split-adjusted close/open | Tiingo split-adjusted close/open | Tiingo split-adjusted close/open | **Identical** |
| **Transaction Friction** | 15 bps round-trip | 15 bps round-trip | 15 bps round-trip | **Identical** |
| **Transaction Costs Deducted** | \$153.65 | \$154.41 | \$153.65 | **Identical** |
| **Truncated Ticker Handling** | BLK, CSCO, CVS, EQIX, FCX exit on last valid bar | BLK, CSCO, CVS, EQIX, FCX exit on last valid bar | BLK, CSCO, CVS, EQIX, FCX exit on last valid bar | **Identical** |
| **Final Portfolio Equity** | **\$104,709.12** | **\$105,724.86** | **\$104,709.12** | **Exact Parity** |
| **Total Net Return** | **+4.71%** | **+5.72%** | **+4.71%** | **Exact Parity** |
| **Maximum Drawdown** | **-35.35%** | **-35.35%** | **-35.35%** | **Exact Parity** |
| **Annualized Sharpe** | **0.35** | **0.39** | **0.35** | **Exact Parity** |
| **Closed Trades (Win Rate)** | 60 (41.7%) | 60 (50.0%) | 60 (41.7%) | **Exact Parity** |

### 2.3 Reproduction Proof

Executing both configurations in the deterministic simulator yields:
```
Equal-Weight B&H (188 ses)   $104,709.12    +4.71%   -35.35%   Sharpe: 0.35   Trades: 60 (41.7% win)   Costs: $153.65
Equal-Weight B&H (180 ses)   $105,724.86    +5.72%   -35.35%   Sharpe: 0.39   Trades: 60 (50.0% win)   Costs: $154.41
```
The exact mathematical cause is validated: both figures are legitimate outcomes of holding for 188 versus 180 market sessions. In Phase 5K.1, the primary benchmark is aligned to the 188-session series (+4.71%), perfectly matching Phase 5J.

---

## 3. Clarify Zero-Trade Model Results

### 3.1 Candidate Signal Funnel Diagnostics

Across all $N = 10,559$ out-of-sample observations evaluated across the 4 chronological outer folds, each model was submitted to identical institutional risk gates and portfolio constraints:
- **Round-trip transaction costs:** 15.0 bps (2.5 entry, 2.5 exit, 2.5 half-spread, 2.5 slippage)
- **Minimum net return hurdle:** $+0.50\%$ (minimum gross return $+0.65\%$)
- **Directional BUY threshold:** $+1.50\%$ net return (gross return $\ge +1.65\%$)
- **Uncertainty ceiling:** $\sigma_{\text{train}} \le 0.0800$ (enforced)
- **Defensive Volatility Gate:** Rolling 5-day market volatility $\sigma_{\text{vol}} \le 0.1500$ (enforced)
- **Portfolio capacity:** 10 maximum concurrent positions, 10% target allocation

The following table summarizes candidate signal generation and gate interception for all evaluated models:

| Candidate Model / Policy | Raw Preds $\ge +1.50\%$ | Raw Preds $\ge +1.65\%$ | Volatility Gate Breaches ($>0.15$) | Cost Hurdle Breaches ($<0.0065$) | Directional Threshold Hold ($<1.50\%$) | Cleared BUY Signals | Simulator Executed Trades | Rejection Breakdown (Simulator) | Final Policy Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Reference 0: Zero Return** | 0 | 0 | 7,325 | 3,234 | 0 | 0 | 0 | None | *no positions executed under fixed policy* |
| **Reference 1: Historical Median** | 0 | 0 | 7,325 | 2,104 | 1,130 | 0 | 0 | None | *no positions executed under fixed policy* |
| **Ridge Regression (Phase 5J Benchmark)** | 2,755 | 2,548 | 7,325 | 5,311 | 522 | **112** | **44** | 44 `MAX_TICKER_EXPOSURE`<br>24 `CONCURRENT_LIMIT` | *active positions executed under fixed policy* |
| **ElasticNet ($L_1 + L_2$ Regularized)** | 0 | 0 | 7,325 | 10,382 | 51 | 0 | 0 | None | *no positions executed under fixed policy* |
| **HistGradientBoosting (Nonlinear GBRT)** | **235** | **235** | **7,325** | 8,426 | 147 | 0 | 0 | None | *no positions executed under fixed policy* |
| **Ridge CS Demeaned** | 227 | 215 | 7,325 | 5,741 | 1,745 | 0 | 0 | None | *no positions executed under fixed policy* |
| **Ridge CS Scaled** | 227 | 215 | 7,325 | 5,741 | 1,745 | 0 | 0 | None | *no positions executed under fixed policy* |
| **Ridge Sector Neutral** | 145 | 136 | 7,325 | 9,427 | 62 | 0 | 0 | None | *no positions executed under fixed policy* |

### 3.2 Categorized Reasons for Zero Trades

1. **HistGradientBoosting:**
   - **Candidate BUY Signals Generated:** 235 predictions cleared the $+1.65\%$ gross return hurdle ($\ge +1.50\%$ net return).
   - **Primary Interception Cause:** 100% of these 235 candidate signals were generated during high-volatility sessions where rolling 5-session market volatility exceeded the safe ceiling ($\sigma_{\text{vol}} > 0.1500$). The mean market volatility during these 235 signals was **1.0712** (min $0.1858$, max $2.3789$), coinciding with the March 2020 COVID crash.
   - **Mechanism:** The Phase 5G `VOLATILITY_GATE` intervened as designed, converting all 235 signals to defensive `HOLD` to avoid opening levered equity positions during severe macro dislocations.

2. **ElasticNet:**
   - **Candidate BUY Signals Generated:** 0 predictions cleared the $+1.50\%$ hurdle.
   - **Primary Interception Cause:** Strong $L_1$ penalty shrinkage ($\alpha = 0.01$, $\ell_1 = 0.5$) compressed regression coefficients toward zero. Out of 10,559 out-of-sample forecasts, the maximum positive prediction was $+0.0094$ (+0.94%). Consequently, 10,382 forecasts failed the cost hurdle pre-check ($| \hat{y} | < 0.0065$), and the remaining 51 non-gated forecasts failed the $+1.50\%$ directional BUY threshold.

3. **Cross-Sectional Demeaned & Sector-Neutral Variants:**
   - **Candidate BUY Signals Generated:** 215 signals (CS Demeaned) and 136 signals (Sector Neutral) cleared $+1.65\%$.
   - **Primary Interception Cause:** Like GBRT, 100% of these extreme positive relative forecasts occurred during the high-volatility March 2020 regime and were intercepted by the Volatility Gate.

4. **Ridge Regression Execution Context:**
   - Ridge regression has lower effective shrinkage and a positive forecast bias ($+0.81\%$), producing 2,548 predictions $\ge +1.65\%$.
   - While 7,325 predictions were intercepted by the Volatility Gate, **112 predictions** occurred during calm market regimes ($\sigma_{\text{vol}} \le 0.1500$) and cleared all gates.
   - These 112 BUY signals entered the simulator: 44 were executed into closed trades, 44 were rejected by `MAX_TICKER_EXPOSURE` (already holding a position in that ticker), and 24 were rejected by `MAX_CONCURRENT_POSITIONS` ($112 = 44 + 44 + 24$, 100% accounting reconciliation).

### 3.3 Verification of Identical Gating and Simulator Integrity

- **Identical Policy Gating:** The exact same `RiskGateConfig`, `TransactionCostConfig`, and `PortfolioConfig` were applied across all candidate models without any per-model modification.
- **Simulator Capital Accounting:** When zero trades were opened, the simulator reported:
  - Initial Cash: \$100,000.00
  - Final Equity: \$100,000.00
  - Total Net Return: 0.00%
  - Maximum Drawdown: 0.00%
  - Total Transaction Costs: \$0.00
  - Sharpe Ratio: 0.00
- **Policy Interpretation:** Zero-trade results are not evidence that ElasticNet or GBRT are inferior portfolio strategies, nor evidence that Ridge is superior. They demonstrate that under the **fixed, un-tuned institutional policy**, models with heavy shrinkage or signals concentrated in high-volatility regimes correctly held 100% cash rather than generating un-hedged trades during crisis regimes.

---

## 4. Preservation of Research Integrity

In accordance with strict empirical research standards:
1. **No Tuning on Validation Data:** Decision thresholds ($+1.50\%$), cost hurdles (15 bps), volatility caps ($0.1500$), and model hyperparameters were held strictly fixed.
2. **HistGradientBoosting Empirical Finding:** The Phase 5K core finding is fully preserved:
   - **Forecasting Error:** HistGradientBoosting slightly reduces aggregate RMSE ($0.0644$ vs $0.0652$ for Ridge, $0.0646$ for Zero Return) and MAE ($0.0393$ vs $0.0399$ for Ridge).
   - **Cross-Sectional Stock-Picking Edge:** The mean daily cross-sectional Spearman rank IC is **$-0.0267$** with a Newey-West HAC standard error of $0.0354$ ($p = 0.4512$). It is statistically indistinguishable from zero. GBRT provides no proven daily stock-ranking edge.
3. **No Promotion to Production:** As mandated by the governance framework, experimental candidate models are retained in the research sandbox and not promoted to live decision generation.

---

## 5. Artifacts Regenerated & Code Modifications

1. `scripts/evaluate_phase5k.py`:
   - Updated Buy-and-Hold simulation to compute both the 188-session primary benchmark (+4.71%, matching Phase 5J) and the 180-session decision-window variant (+5.72%).
   - Integrated candidate signal counters, gate rejection breakdowns, and explicit `"policy_status": "no positions executed under the fixed policy"` labeling for all models.
   - Added `benchmark_reconciliation` and `zero_trade_reconciliation` metadata sections to the master JSON artifact.
2. `data/processed/research/phase5k/phase5k_model_experiment_results.json`:
   - Regenerated with reconciled 188-session primary B&H benchmark (\$104,709.12, +4.71%) and explicit zero-trade diagnostic metrics.
3. `frontend/src/components/PredictionResearchTab.jsx`:
   - Added Equal-Weight Buy & Hold reconciled benchmark row directly into the Phase 5K performance table.
   - Labeled zero-trade entries explicitly as `0 (No positions executed)` with tooltip explanations.
   - Replaced raw LaTeX math escapes with clean JSX-safe notation to eliminate Vite build errors.

---

## 6. Verification Commands & Execution Results

All verification commands were executed directly in the project environment:

### Command 1: Phase 5K Master Evaluation & Reconciliation Script
```powershell
python scripts/evaluate_phase5k.py
```
- **Exit Code:** 0
- **Key Output:**
  - `Equal-Weight B&H (188 ses)`: \$104,709.12, Net Return: +4.71%, Max DD: -35.35%, Sharpe: 0.35, Closed Trades: 60 (41.7% win rate)
  - `Equal-Weight B&H (180 ses)`: \$105,724.86, Net Return: +5.72%, Max DD: -35.35%, Sharpe: 0.39, Closed Trades: 60 (50.0% win rate)
  - Zero-trade models reported: \$100,000.00, +0.00%, Max DD: 0.00%, Sharpe: 0.00, Trades: 0, labeled `[No Positions Executed]`
  - Ridge model reported: \$100,882.49, +0.88%, Max DD: -4.03%, Sharpe: 0.26, Trades: 44, Rejections: 68 (112 BUY signals reconciled)
  - Generated: `data/processed/research/phase5k/phase5k_model_experiment_results.json`

### Command 2: Focused Unit & Integration Tests (Phase 5K & Phase 5J)
```powershell
python -m pytest tests/test_phase5k_model_improvement.py tests/test_phase5j_cross_sectional.py
```
- **Exit Code:** 0
- **Result:** `16 passed, 1 warning in 4.51s`

### Command 3: Full Repository Test Suite
```powershell
python -m pytest
```
- **Exit Code:** 0
- **Result:** `188 passed, 1 warning in 26.12s`
- **Coverage:** All 20 test modules passed including API, dataset builder, decision layer, features, SEC ingestion, portfolio simulation, and temporal validation audit.

### Command 4: Production Frontend Build
```powershell
cd frontend && npm run build
```
- **Exit Code:** 0
- **Result:** `✓ built in 708ms` (dist/index.html, dist/assets/index-*.js, dist/assets/index-*.css cleanly generated).

---

## 7. Deliverable Signoff & Final Verdict

| Check | Requirement | Result |
| :--- | :--- | :---: |
| **1. B&H Reconciled** | Root cause identified, both +4.71% and +5.72% reproduced and explained | **PASS** |
| **2. Zero-Trade Breakdown** | Candidate signals counted, gate rejections categorized, identical gating verified | **PASS** |
| **3. Simulator Integrity** | Cash preservation (\$100k), 0 drawdown, and 0 costs verified when 0 trades opened | **PASS** |
| **4. Explicit Labeling** | Zero-trade results labeled "no positions executed under the fixed policy" | **PASS** |
| **5. Research Integrity** | No model retuning, outer boundaries intact, GBRT empirical reality preserved | **PASS** |
| **6. Automated Verification**| Full test suite (188 tests) and frontend build pass with 0 errors | **PASS** |

### Final Verdict: ACCEPT WITH DOCUMENTED LIMITATIONS
- **Limitation 1:** Nonlinear GBRT reduces aggregate forecast RMSE (0.0644 vs 0.0652) but offers no statistically demonstrable daily cross-sectional ranking alpha ($p = 0.4512$).
- **Limitation 2:** Under the fixed Phase 5G policy, shrunk models (ElasticNet, GBRT) generate zero funded trades because extreme forecasts coincide with high-volatility COVID market regimes filtered out by defensive risk gates.
- **Limitation 3:** The Buy-and-Hold benchmark is sensitive to the terminal liquidation date (+4.71% at session 188 post-pullback vs +5.72% at session 180 pre-pullback); both are documented for transparent historical comparison.
