# Phase 5K — Systematic Model Improvement and Walk-Forward Validation Design

## 1. Executive Summary & Research Mandate

Phase 5K advances the financial intelligence agent from the baseline established in Phase 5J/5J.1 into a systematic, hypothesis-driven exploration of predictive models and cross-sectional representations. The project remains **experimental quantitative finance research** conducted within strict institutional constraints.

### Core Research Tenets
1. **Zero Data Fabrication & Universe Invariance**: Retains the audited 60-company S&P 500 cohort across 11 GICS sectors without downloading external unverified data, acquiring paid APIs, expanding the universe, or tampering with forward target definitions.
2. **Strict Chronological Isolation**: Preserves the 4-fold walk-forward schedule with a mandatory **5-session purge gap** between training and out-of-sample testing to neutralize label overlap leakage ($H=5$ forward returns).
3. **Training-Only Preprocessing & Tuning**: Imputers, scalers, and hyperparameter grids ($\alpha, l_1, \text{depth}, \lambda$) are calibrated strictly within outer training partitions via internal chronological date-grouped validation. Outer validation data is never inspected during model tuning.
4. **Honest Dependence-Aware Inference**: Rejects misleading pooled i.i.d. $p$-values. Evaluates cross-sectional stock-picking skill using daily cross-sectional Spearman Rank IC adjusted for 4-day serial autocorrelation via Newey–West Heteroskedasticity and Autocorrelation Consistent (HAC) inference ($L=4$).
5. **Separation of Forecasting Error from Portfolio Execution**: Models are evaluated first on point-forecast error and ranking ability, and second on institutional portfolio simulation under 15 bps round-trip transaction friction.

---

## 2. Walk-Forward Schedule and Panel Composition

### Panel Dimensions
- **Cohort Universe**: 60 companies representing all 11 GICS sectors (`data/processed/universe/phase5j_company_eligibility.csv`).
- **Research Evaluation Window**: `2019-01-02` to `2020-06-10` (warmed with market quotes from `2018-01-01`).
- **Scored Out-of-Sample Population**: Exactly **10,559 valid observations** across 180 distinct calendar sessions.
  - Folds 0–2: 60 active companies ($2,700$ rows in Fold 0; $2,700$ rows in Fold 1; $2,685$ rows in Fold 2).
  - Fold 3: 55 active companies ($2,474$ rows). Five companies (`BLK`, `CSCO`, `CVS`, `EQIX`, `FCX`) terminate market quotes on `2020-04-01` and are deterministically excluded from Fold 3 evaluation with zero synthetic imputation.

### Chronological Fold Schedule
$$\text{Outer Fold } k: \quad \mathcal{D}_{\text{train}}^{(k)} \xrightarrow{\text{Purge Gap } (5 \text{ sessions})} \mathcal{D}_{\text{val}}^{(k)}$$

| Outer Fold | Train Sessions | Train Date Window | Val Sessions | Val Date Window | Macro / Market Regime | Active Tickers | Val Observations |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Fold 0** | 173 | 2019-01-02 $\to$ 2019-09-09 | 45 | 2019-09-17 $\to$ 2019-11-18 | Late 2019 Steady Expansion | 60 | 2,700 |
| **Fold 1** | 218 | 2019-01-02 $\to$ 2019-11-11 | 45 | 2019-11-19 $\to$ 2020-01-24 | Pre-COVID All-Time Highs | 60 | 2,700 |
| **Fold 2** | 263 | 2019-01-02 $\to$ 2020-01-16 | 45 | 2020-01-27 $\to$ 2020-03-30 | COVID-19 Crash ($-35\%$) | 60 | 2,685 |
| **Fold 3** | 308 | 2019-01-02 $\to$ 2020-03-23 | 45 | 2020-03-31 $\to$ 2020-06-03 | Aggressive Fed / Macro Recovery | 55 | 2,474 |

### Target Definition Invariant
The target variable strictly mirrors the institutional execution convention established in Phase 5C:
$$y_{i,t} = \frac{P_{i, t+5, \text{close}}^{\text{adj}} - P_{i, t+1, \text{open}}^{\text{adj}}}{P_{i, t+1, \text{open}}^{\text{adj}}}$$
Decision at Session $T$ market close $\to$ Executable Entry at Session $T+1$ opening auction $\to$ Executable Exit at Session $T+5$ market close.

---

## 3. Pre-Specified Candidate Models

To prevent data dredging and unconstrained model searching, Phase 5K pre-specifies five distinct model architectures across linear, regularized, and nonlinear paradigms:

### Candidate A: Naive Zero-Return Benchmark (`zero_baseline`)
- **Mathematical Form**: $\hat{y}_{i,t} = 0.0, \quad \forall i, t$.
- **Purpose**: Establishes the variance-free baseline. In noisy financial return prediction where signal-to-noise is below $5\%$, any model attempting to predict return variance incurs a parameter variance penalty that frequently exceeds zero.

### Candidate B: Historical Median Benchmark (`median_baseline`)
- **Mathematical Form**: $\hat{y}_{i,t} = \text{median}\left(\{ y_{j,\tau} \in \mathcal{D}_{\text{train}} \}\right)$.
- **Purpose**: Captures trailing market drift strictly from past data. Evaluates whether a simple trailing central-tendency estimate outperforms unconditional zero.

### Candidate C: Existing Cross-Sectional Ridge Regression (`ridge_regression`)
- **Mathematical Form**:
  $$\min_{\boldsymbol{\beta}} \sum_{n=1}^{N_{\text{train}}} \left( y_n - \mathbf{x}_n^T \boldsymbol{\beta} \right)^2 + \alpha \|\boldsymbol{\beta}\|_2^2$$
- **Feature Space**: 17 standard technical market indicators (`market_return_1d`, `market_return_5d`, `market_volatility_5d`, `market_momentum_5d`, `market_rsi_14d`, `market_zscore_20d`, etc.).
- **Tuning**: Grid search over $\alpha \in \{0.01, 0.1, 1.0, 10.0, 100.0, 1000.0\}$ using an internal chronological 70/30 date-split within each outer training fold.

### Candidate D: ElasticNet Regression (`elastic_net`)
- **Mathematical Form**:
  $$\min_{\boldsymbol{\beta}} \frac{1}{2 N_{\text{train}}} \sum_{n=1}^{N_{\text{train}}} \left( y_n - \mathbf{x}_n^T \boldsymbol{\beta} \right)^2 + \alpha \left( \rho \|\boldsymbol{\beta}\|_1 + \frac{1 - \rho}{2} \|\boldsymbol{\beta}\|_2^2 \right)$$
- **Purpose**: Tests whether sparse feature selection ($L_1$ penalty) combined with shrinkage ($L_2$ penalty) filters out uninformative technical indicators and reduces overfitting.
- **Tuning**: Inner chronological grid search over $\alpha \in \{0.0005, 0.001, 0.01, 0.1\}$ and $l_1\text{-ratio } \rho \in \{0.1, 0.5, 0.7\}$ with convergence tolerance $10^{-3}$.

### Candidate E: Non-Linear Gradient-Boosted Trees (`hist_gradient_boosting`)
- **Mathematical Form**:
  $$\hat{y}_{i,t} = \sum_{m=1}^M \gamma_m f_m(\mathbf{x}_{i,t}), \quad f_m \in \mathcal{F}_{\text{trees}}$$
- **Purpose**: Tests whether non-linear decision boundaries and feature interactions (e.g., momentum conditional on extreme volatility) improve out-of-sample forecasts without severe tabular overfitting.
- **Regularization Safeguards**:
  - Shallow tree depths: $\text{max\_depth} \in \{2, 3\}$ (maximum 4 to 8 terminal leaves).
  - High minimum leaf weight: $\text{min\_samples\_leaf} = 50$ (prevents memorization of individual stock outliers).
  - Conservative shrinkage: $\text{learning\_rate} \in \{0.01, 0.02\}$, $\text{max\_iter} = 50$.
  - Explicit $L_2$ leaf regularization: $\lambda \in \{1.0, 10.0\}$.

---

## 4. Targeted Cross-Sectional and Sector Hypotheses

### Hypothesis 1: Cross-Sectional Demeaning / Market-Drift Neutralization
- **Rationale**: In Phase 5J, Ridge underperformed the Zero baseline in Fold 2 because the model entered the COVID crash expecting a positive bull market drift ($+1.09\%$) while actual returns collapsed to $-1.85\%$. By demeaning predictions cross-sectionally on each trading date $t$, market-wide macro bias is eliminated at the decision timestamp:
  $$\hat{y}_{i,t}^{\text{cs-demeaned}} = \hat{y}_{i,t} - \frac{1}{N_t} \sum_{j=1}^{N_t} \hat{y}_{j,t}$$
- **Mathematical Constraint**: Because rank correlation is completely invariant to additive constants ($IC(\hat{y}_t - c_t, y_t) \equiv IC(\hat{y}_t, y_t)$), cross-sectional demeaning cannot mathematically alter daily rank IC. However, it alters raw forecast error (RMSE/MAE) and directional sign alignment.

### Hypothesis 2: Sector-Neutral Residualization
- **Rationale**: Cross-sectional equity returns are dominated by sector co-movement. If a model simply bets on high-beta sectors (e.g., Information Technology) rather than idiosyncratic stock quality, its rank IC will be volatile across sector rotations.
- **Mathematical Specification**: On each trading date $t$, for stock $i$ belonging to GICS sector $s(i)$:
  $$\hat{y}_{i,t}^{\text{sector-neutral}} = \hat{y}_{i,t} - \frac{1}{|S_{s(i), t}|} \sum_{j \in S_{s(i), t}} \hat{y}_{j,t}$$
  where $S_{s,t}$ is the set of active equities in sector $s$ at date $t$.
- **Integrity Requirement**: Sector classifications are derived from verified canonical SEC filings (`data/processed/universe/phase5j_company_eligibility.csv`).

---

## 5. Statistical Inference Protocol

### Econometric Pitfall: Overlapping Label Autocorrelation
Because 5-session forward returns overlap by 4 sessions between consecutive trading days $T$ and $T+1$, the residual time series exhibits an inherent Moving Average process of order 4 ($MA(4)$):
$$\text{Cov}(u_t, u_{t+k}) \neq 0 \quad \text{for } |k| < 5$$

### Standard Error & HAC Inference
1. **Daily Cross-Sectional Rank IC**:
   $$IC_t = \text{Spearman}\left( \{ \hat{y}_{i,t} \}_{i=1}^{N_t}, \{ y_{i,t} \}_{i=1}^{N_t} \right)$$
2. **Newey–West HAC Variance Estimator ($L=4$)**:
   $$\hat{V}_{\text{HAC}} = \hat{\gamma}_0 + 2 \sum_{l=1}^4 \left( 1 - \frac{l}{5} \right) \hat{\gamma}_l, \quad \text{where } \hat{\gamma}_l = \frac{1}{T-l} \sum_{t=l+1}^T (IC_t - \overline{IC})(IC_{t-l} - \overline{IC})$$
   $$SE_{\text{HAC}} = \sqrt{\frac{\hat{V}_{\text{HAC}}}{T_{\text{dates}}}}, \quad t_{\text{HAC}} = \frac{\overline{IC}}{SE_{\text{HAC}}}, \quad p_{\text{HAC}} = 2 \left( 1 - F_{t(T-1)}(|t_{\text{HAC}}|) \right)$$

---

## 6. Portfolio Simulation and Order Reconciliation

Out-of-sample predictions from candidate models are piped through the identical deterministic portfolio engine:

### Portfolio Execution Parameters
- **Initial Portfolio Capital**: $\$100,000.00$ in cash.
- **Maximum Concurrent Positions**: 10 positions.
- **Maximum Individual Asset Weight**: $10\%$ target allocation ($\$10,000$ per position).
- **Holding Horizon**: Exactly 5 trading sessions (entry at $T+1$ open, exit at $T+5$ close).
- **Transaction Friction**: 15 bps round-trip (2.5 bps entry fee, 2.5 bps exit fee, 2.5 bps half-spread, 2.5 bps slippage).
- **Risk Gate Controls**:
  - Provenance Gate: Rejects requests where decision date precedes training cutoff.
  - Uncertainty Ceiling Gate: Rejects if $\sigma_{\text{train}} > 0.08$.
  - Fixed Return Hurdle: $\text{BUY} \iff \hat{y}_{\text{net}} \ge +0.015$; $\text{SELL} \iff \hat{y}_{\text{net}} \le -0.015$.

### Strict Order Reconciliation Formula
$$\text{Candidate BUY Orders} \equiv \text{Executed Closed Trades} + \text{Rejected Orders} + \text{Terminal Open Positions}$$
Rejection reasons (`MAX_TICKER_EXPOSURE` and `CONCURRENT_LIMIT_REACHED`) are cataloged deterministically.
Daily mark-to-market accounting must satisfy:
$$\text{Equity}_t = \text{Cash}_t + \text{InvestedCapital}_t \quad (\Delta < \$0.0001)$$
across all 180 out-of-sample trading sessions.
