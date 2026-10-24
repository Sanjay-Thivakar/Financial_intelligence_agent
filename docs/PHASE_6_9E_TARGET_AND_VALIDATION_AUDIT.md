# PHASE 6.9E — TARGET, LABEL, AND VALIDATION AUDIT REPORT

**Lead Quantitative Researcher & Model Risk Auditor**: AI-Powered Financial Intelligence Agent Architecture Team  
**Audit Date**: October 2026  
**Phase**: Phase 6.9E (Predictive Signal Diagnosis & Model Improvement)  
**Target Code & Artifacts Audited**:
- Target Engine: [`src/features/target.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/target.py)
- Splitter Engine: [`src/models/splitter.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/models/splitter.py)
- Research Dataset: [`data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet)
- Diagnostic Summary: [`data/processed/research/phase6_9e/phase6_9e_diagnostic_summary.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase6_9e/phase6_9e_diagnostic_summary.json)

---

## 1. Executive Summary

This audit rigorously inspected the target construction, corporate action adjustments, temporal boundaries, cross-validation mechanisms, and variance characteristics of the forward return target across the canonical 305-company cohort (110,105 observations, 361 trading sessions).

### Key Audit Findings:
1. **Target Mechanics Are Mechanically Leakage-Free**: The 5-day forward return target correctly computes holding from Session $T+1$ Open to Session $T+5$ Close using backward-adjusted total return pricing.
2. **Purge Gaps Are Strictly Enforced**: The 5-session purge gap in trading-day units strictly eliminates target label overlap between training and validation folds across all 4 walk-forward splits.
3. **Core Target Design Defect Identified**: The target is formulated as an **un-demeaned raw forward return**. In our 305-company universe, **41.2% of target return variance is driven by the daily market-wide common factor** (S&P 500 macro drift). This forces models to conflate macro market timing with cross-sectional stock selection, drowning out stock-specific fundamental and event signals.
4. **Three-Session Holdout Is Insufficient**: The post-June 3, 2020 period contains only 3 trading sessions (915 observations), which cannot statistically evaluate out-of-sample generalization.

---

## 2. Target Formulation and Pricing Mechanics

### 2.1 Mathematical Formulation
The target represents the total arithmetic return over a 5-trading-session holding horizon:
$$y_T^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$

Under the project timing convention:
- **Decision Timestamp ($T$)**: Session $T$ Market Close (16:00:00 US Eastern Time $\to$ UTC). All feature variables are locked strictly as of this timestamp.
- **Trade Entry Timestamp ($T+1$)**: Session $T+1$ Market Open (09:30:00 US Eastern Time $\to$ UTC). Feasible execution price is $P_{T+1, \text{open}}$.
- **Trade Exit Timestamp ($T+5$)**: Session $T+5$ Market Close (16:00:00 US Eastern Time $\to$ UTC). Feasible exit price is $P_{T+5, \text{close}}$.

### 2.2 Price Fields and Corporate Action Adjustment
- Source price fields: `open`, `close`, `adjusted_close`.
- Derived adjusted open:
  $$\text{factor}_t = \frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}}$$
  $$P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times \text{factor}_t$$
- **Audit Verification**:
  1. The adjustment factor accounts for stock splits, stock dividends, and cash distributions on a total return basis.
  2. Because the entire historical price panel was generated from backward-adjusted prices, $P_{T+1, \text{open}}^{\text{adj}}$ and $P_{T+5, \text{close}}^{\text{adj}}$ share an identical corporate action adjustment denominator, eliminating synthetic dividend or split drop-downs.
  3. No negative, zero, or null prices exist in the price series across all 305 companies.

### 2.3 Handling of Missing Data, Delistings, and Incomplete Horizons
- **Cohort Stability**: Evaluated across the verified 305-company cohort ([`data/processed/universe/phase6_9a1_cohort_manifest.csv`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/universe/phase6_9a1_cohort_manifest.csv)), preserving surviving and predecessor corporate identities (e.g., Concho Resources `CXO` CIK `0001358071` and Apache Corp `APA` predecessor CIK `0000006769`).
- **Terminal Masking**: In [`src/features/target.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/target.py), the terminal 5 sessions of each company series are explicitly masked (`target_forward_return_5d_valid = False` and `target_forward_return_5d = NaN`). Only observations with complete 5-day forward horizons enter the research dataset.

---

## 3. Validation Design and Split Boundary Verification

### 3.1 Purge Gap and Holding Window Isolation
The walk-forward splitter ([`src/models/splitter.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/models/splitter.py)) enforces expanding chronological cross-validation:
- Minimum training sessions: 173
- Validation sessions per fold: 45
- Purge sessions: 5

#### Rigorous Proof of Zero Window Overlap:
Let $t \in [0, 360]$ represent the globally ordered trading calendar indices.

| Fold | Last Train Decision ($t_{\text{tr}}$) | Last Train Target Exit ($t_{\text{tr}} + 5$) | Purge Gap Sessions | First Val Decision ($t_{\text{val}}$) | First Val Entry ($t_{\text{val}} + 1$) | Separation Margin |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0** | Index 172 (`2019-09-09`) | Index 177 (`2019-09-16` Close) | 5 sessions (Indices 173–177) | Index 178 (`2019-09-17` Close) | Index 179 (`2019-09-18` Open) | **+1 session** strictly before decision |
| **1** | Index 217 (`2019-11-11`) | Index 222 (`2019-11-18` Close) | 5 sessions (Indices 218–222) | Index 223 (`2019-11-19` Close) | Index 224 (`2019-11-20` Open) | **+1 session** strictly before decision |
| **2** | Index 262 (`2020-01-16`) | Index 267 (`2020-01-24` Close) | 5 sessions (Indices 263–267) | Index 268 (`2020-01-27` Close) | Index 269 (`2020-01-28` Open) | **+1 session** strictly before decision |
| **3** | Index 307 (`2020-03-23`) | Index 312 (`2020-03-30` Close) | 5 sessions (Indices 308–312) | Index 313 (`2020-03-31` Close) | Index 314 (`2020-04-01` Open) | **+1 session** strictly before decision |

**Verification**: In all 4 folds, the last training trade has completely settled and exited before the first validation decision is formed. Target label leakage across split boundaries is **identically zero**.

### 3.2 Preprocessing and Leakage Isolation
1. **Scaler and Imputer Fitting**: Imputers (`SimpleImputer(strategy="median")`) and standardizers (`StandardScaler()`) are fit exclusively on the outer training fold (`tr_df`) and applied out-of-sample via `transform()`.
2. **Inner Hyperparameter Tuning**: Inner validation splits use the earliest 70% unique dates of the training fold, fitting inner scalers strictly on the inner training portion.
3. **Identifier Isolation**: Company IDs, tickers, trading dates, and target metadata are excluded from model input matrices.

---

## 4. The Core Target Design Defect: Target Variance Decomposition

### 4.1 Empirical Variance Breakdown
In institutional quantitative finance, stock return forecasts can target:
- **Raw Return**: $R_{i, t+1 \to t+5}$ (Un-demeaned total return)
- **Market-Neutral Excess Return**: $R_{i, t+1 \to t+5} - \bar{R}_{mkt, t+1 \to t+5}$
- **Cross-Sectional Rank**: $\text{Rank}(R_{i, t+1 \to t+5}) / N$

We decomposed the total empirical variance of `target_forward_return_5d` across all 110,105 observations:

$$\text{Var}(y_i) = \text{Var}(\bar{y}_{mkt}) + \text{Var}(y_i - \bar{y}_{mkt})$$

| Component | Empirical Variance | Percentage of Total Variance | Financial Interpretation |
| :--- | :---: | :---: | :--- |
| **Total Target Variance** | `0.003340` | **100.0%** | Combined return variability across all stocks and sessions |
| **Market Common Factor** ($\bar{y}_{mkt}$) | `0.001376` | **41.2%** | Broad market macro drift (S&P 500 macro trends, COVID crash/recovery) |
| **Idiosyncratic Cross-Sectional** | `0.001964` | **58.8%** | Stock-specific relative performance |

### 4.2 Why Raw Return Formulation Harms Fundamental & Event Modeling
1. **Macro Noise Dominance**: Over 40% of the variance in raw 5-day return is purely common market beta. When a pooled linear regression is trained on raw returns, it naturally weights features that correlate with market-wide volatility and momentum regimes to minimize squared error across the macro cycle.
2. **Feature Scale Mismatch**: Stock-specific accounting ratios (e.g. Net Margin, ROA, Debt/Equity) and 8-K filing occurrences contain **zero macro timing signal**. A company with a high ROA is not predictive of whether the Federal Reserve will cut rates or whether the market will crash next week.
3. **Signal Cancellation**: Forcing fundamental and event features into a raw return model dilutes the model's capacity, while technical momentum indicators pick up macro time-series correlations.
4. **Empirical Proof**:
   - Correlation of `fundamental_ratio_roa` with raw target: $r = +0.0107$ ($p = 4.3 \times 10^{-4}$).
   - Correlation of `fundamental_ratio_roa` with market-neutral excess target: **$r = +0.0296$ ($p = 1.6 \times 10^{-22}$)**!
   - Removing the market common factor increases the statistical significance of fundamental accounting features by **18 orders of magnitude**.

---

## 5. Audit of the Final Holdout Horizon

### 5.1 Holdout Size and Statistical Power
- The available research panel spans `2019-01-02` to `2020-06-08` (361 sessions).
- Walk-forward validation ends on session index 357 (`2020-06-03`).
- The remaining sessions post June 3, 2020 are:
  - Session 358 (`2020-06-04`)
  - Session 359 (`2020-06-05`)
  - Session 360 (`2020-06-08`)
- Total holdout observations: $3 \times 305 = 915$ rows.

### 5.2 Holdout Inadequacy Determination
- In time-series financial econometrics, 3 trading sessions represent only **0.6 calendar weeks** and **zero independent 5-day forward return windows** (since all 3 sessions have overlapping 5-day return holding periods).
- Evaluating model variants repeatedly on 3 calendar days provides zero statistical degrees of freedom ($T=3$) and creates severe risks of false discovery.
- **Auditor Invariant**: The 3-session holdout must remain strictly quarantined and untouched. A legitimate final holdout will require historical data expansion (e.g., Q3–Q4 2020 or 2021) with at least 40–60 non-overlapping trading sessions.

---

## 6. Audit Conclusions & Prescriptions

| Dimension | Audit Finding | Verdict | Action Required |
| :--- | :--- | :---: | :--- |
| **Formula & Price Fields** | Verified backward-adjusted $T+1$ Open to $T+5$ Close | **PASS** | Maintain existing execution timing contract |
| **Purge Gap Implementation** | 5-session gap eliminates holding window overlap | **PASS** | Preserve 5-session purge in all future splits |
| **Temporal Preprocessing** | Training-only scaling, imputer, and tuning | **PASS** | Strict zero-leakage invariant maintained |
| **Target Formulation** | Raw return conflates macro beta with stock alpha | **DEFECT** | **Prescribe cross-sectional demeaning ($y_i - \bar{y}_{mkt}$) for alpha models** |
| **Holdout Buffer** | 3 sessions post June 3, 2020 insufficient for testing | **LIMITATION** | **Keep holdout untouched; expand historical archive in Phase 7** |
