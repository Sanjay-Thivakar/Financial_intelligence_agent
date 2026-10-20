# Phase 5G — Decision & Risk Layer Architecture and Design Specification

**Phase**: 5G  
**Component**: Decision & Risk Layer (BUY / HOLD / SELL Experimental Candidate Signals)  
**Status**: Architecture & Design Specification  
**Date**: October 2026  
**Disclaimer**: This document specifies a research decision-support and risk-gating system. It does **not** constitute personalized investment advice, trading recommendations, or a guarantee of profitability.

---

## 1. System Objective & Research Context

The objective of Phase 5G is to bridge the gap between statistical model forecasts and institutional decision support by constructing an explicit, explainable, and defensively risk-gated **Decision & Risk Layer**.

### 1.1 Context from Preceding Phases
- **Phase 4C**: Established the unified multi-modal feature architecture and point-in-time alignment at the `NEXT_SESSION_OPEN` (09:15 ET) decision cutoff.
- **Phase 5C & 5D**: Evaluated market-only and market-plus-fundamentals Ridge baselines, discovering that quarterly SEC facts operate on a frequency mismatch with 5-day horizon targets, and that naive baselines (Historical Median) are competitive.
- **Phase 5F & 5F.1**: Integrated point-in-time Form 8-K event features across `AAPL`, `JPM`, `GOOG`, `TSLA`. The evaluation showed that event features lowered MAE marginally (from `0.0475` to `0.0472`), matching the Historical Median baseline (`0.0472`), with asset-level degradation in `JPM` (+0.00042 MAE).
- **Critical Takeaway**: Because raw directional return forecasts exhibit high uncertainty and modest information coefficients (IC $\sim +0.06$ to $+0.12$), **a forecast must never be naively translated into a trade signal without cost deductions, uncertainty penalties, and risk controls.**

---

## 2. Mandatory Pre-Implementation Audit Findings

An audit of the production API (`src/api/app.py`), service layer (`src/api/service.py`), and evaluation artifacts confirmed:
1. **Production Dashboard Model**: The current dashboard inference engine (`/api/models/predict`) uses a **Market-Only Ridge regression model** ($\alpha = 1000.0$) trained strictly on historical sessions (`2019-01-02` to `2020-03-23`, Fold 3 training set) across the 4 verified companies.
2. **Feature Schema**: 17 technical market indicators (momentum, volatility, moving average ratios, RSI, volume metrics).
3. **Target Definition**: 5-session forward return ($H = 5$), defined as return from session $T+1$ open to session $T+5$ close:
   $$R_{T+1 \to T+5} = \frac{P_{T+5,\text{close}} - P_{T+1,\text{open}}}{P_{T+1,\text{open}}}$$
4. **Current Application State**: The production API currently produces continuous forward return forecasts (e.g. `+1.85%`) with explicit disclaimers and explicitly **does not generate BUY/HOLD/SELL signals** (lines 145 & 725 in `src/api/service.py`).
5. **Phase 5F Isolation**: Phase 5F research artifacts reside under `data/processed/sec/eight_k/` and have **not** replaced the dashboard's production inference artifact. Phase 5G respects this boundary: the Decision & Risk Layer can evaluate both the production Market-Only model and experimental multi-modal models without silent model substitution.

---

## 3. Decision Contract Specification

The decision layer operates via an immutable, typed contract with comprehensive input validation.

### 3.1 Input Contract: `DecisionContractRequest`
| Field | Type | Description | Validation Rule |
|---|---|---|---|
| `company_id` | `str` | Canonical CIK-based entity identifier (e.g. `US_CIK_0000320193`) | Must match canonical format; non-empty. |
| `ticker` | `str` | Asset ticker symbol (e.g. `AAPL`) | Excluded tickers (e.g. `AA`) rejected immediately. |
| `decision_timestamp` | `datetime` / `str` | Timestamp of decision cutoff (09:15 ET) | ISO 8601 UTC timestamp; cannot be in future. |
| `target_horizon` | `str` | Standardized horizon label | Must equal `"5-trading-session (T+1 open to T+5 close)"`. |
| `predicted_forward_return` | `float` | Model's raw predicted forward return $\hat{y}$ | Finite float; must be within reasonable bounds $[-0.9, +2.0]$. |
| `forecast_uncertainty` | `Optional[float]` | Residual standard error or prediction interval half-width | If provided, must be $\ge 0.0$. |
| `rolling_volatility_5d` | `Optional[float]` | Annualized or session volatility proxy | Non-negative if supplied. |
| `feature_metadata` | `Dict[str, Any]` | Information about missingness and source status | Must specify feature count and staleness. |
| `model_id` | `str` | Unique identifier of generating model | Must be non-empty string. |
| `model_version` | `str` | Version identifier (e.g. `"1.0.0"`) | Checked against supported model registry. |
| `training_cutoff_date` | `str` | Historical date through which model was trained | Must precede `decision_timestamp`. |
| `cost_config` | `Optional[TransactionCostConfig]` | Explicit fee and slippage parameters | Defaults to standard baseline parameters. |
| `risk_config` | `Optional[RiskGateConfig]` | Thresholds and gating parameters | Defaults to conservative research policy. |

### 3.2 Output Contract: `DecisionContractResponse`
| Field | Type | Description |
|---|---|---|
| `signal` | `SignalType` | Enum: `BUY`, `HOLD`, or `SELL`. |
| `predicted_forward_return` | `float` | Raw forecast return input $\hat{y}$. |
| `expected_net_return` | `float` | Net forecast return after cost and slippage deductions: $\hat{y}_{\text{net}} = \hat{y} - C_{\text{roundtrip}}$ (for BUY). |
| `estimated_uncertainty` | `Optional[float]` | Quantitative uncertainty metric used ($\sigma_{\text{resid}}$). |
| `uncertainty_method` | `str` | Description of uncertainty derivation (e.g. `"training_residual_std"`). |
| `threshold_applied` | `float` | Numerical threshold hurdle required for signal activation. |
| `risk_checks_passed` | `List[str]` | List of all risk controls satisfied. |
| `risk_checks_failed` | `List[str]` | List of all risk controls breached. |
| `reasons` | `List[str]` | Transparent, human-readable explanations justifying the signal. |
| `data_quality_warnings` | `List[str]` | Caveats regarding staleness, source coverage, or missing features. |
| `model_provenance` | `Dict[str, Any]` | Verification metadata (model_id, version, training cutoff). |
| `is_experimental` | `bool` | Invariant constant `True` emphasizing non-production status. |

---

## 4. Threshold-Based Decision Logic

### 4.1 Directional Signal Philosophy
- A positive prediction does **not** imply a `BUY`. A `BUY` is emitted only when expected return comfortably clears both transaction costs and a risk-adjusted hurdle threshold, while all risk gates pass.
- A negative prediction does **not** imply a `SELL`. A `SELL` is emitted only when the downward expected return clears costs and the downside threshold, while risk gates pass.
- **Default Action**: The system defaults strictly to `HOLD` whenever evidence is insufficient, uncertainty is elevated, or any risk check fails.

### 4.2 Mathematical Decision Rules
Let:
- $\hat{y}$ = Raw predicted 5-session forward return.
- $C_{\text{roundtrip}}$ = Total estimated round-trip transaction costs and slippage.
- $\sigma$ = Calibrated forecast uncertainty.
- $\theta_{\text{buy}}$ = Configurable BUY threshold (e.g. `+0.015` or $1.5\%$).
- $\theta_{\text{sell}}$ = Configurable SELL threshold (e.g. `-0.015` or $-1.5\%$).
- $\mathcal{G}$ = Boolean conjunction of all risk gate evaluations ($\bigwedge_i g_i$).

Then:
$$\text{Expected Net Return}_{\text{buy}} = \hat{y} - C_{\text{roundtrip}}$$
$$\text{Expected Net Return}_{\text{sell}} = \hat{y} + C_{\text{roundtrip}}$$

The signal is determined by:
$$\text{Signal} = \begin{cases}
\text{BUY} & \text{if } \mathcal{G} = \text{True} \text{ and } \text{Expected Net Return}_{\text{buy}} \ge \theta_{\text{buy}} \\
\text{SELL} & \text{if } \mathcal{G} = \text{True} \text{ and } \text{Expected Net Return}_{\text{sell}} \le \theta_{\text{sell}} \\
\text{HOLD} & \text{otherwise (threshold not cleared, or } \mathcal{G} = \text{False)}
\end{cases}$$

---

## 5. Uncertainty Estimation Methodology

### 5.1 Training-Only Residual Standard Error
To avoid look-ahead bias and future data leakage, uncertainty cannot be derived from test-fold residuals.
- **Method**: For each walk-forward training fold, we compute the standard deviation of in-sample training residuals:
  $$e_i = y_i - \hat{y}_i \quad \forall i \in \mathcal{D}_{\text{train}}$$
  $$\sigma_{\text{resid}} = \sqrt{\frac{1}{N_{\text{train}} - p - 1} \sum_{i=1}^{N_{\text{train}}} (e_i - \bar{e})^2}$$
- **Prediction Interval**: Under normal residual assumptions, an empirical $(1 - \alpha)$ prediction interval is:
  $$\hat{y} \pm z_{1 - \alpha/2} \cdot \sigma_{\text{resid}}$$
- **Conservative Fallback**: If training residuals or uncertainty estimates are unavailable, the uncertainty status is marked `"unavailable"` and the policy forces a conservative `HOLD` if the risk gate requires valid uncertainty.

---

## 6. Configurable Risk Controls

The decision layer enforces six orthogonal risk gates:

1. **Uncertainty Gate (`max_uncertainty`)**:
   - If $\sigma_{\text{resid}} > \sigma_{\max}$ (default: `0.08` or $8.0\%$), signal is forced to `HOLD`.
2. **Cost Hurdle Gate (`min_net_return_hurdle`)**:
   - Net expected return after round-trip costs must exceed a minimum threshold (default: `0.005` or 50 bps).
3. **Data Freshness Gate (`max_staleness_days`)**:
   - Market session must be fresh ($< 4$ calendar days old to account for weekends/holidays). Stale sessions trigger `HOLD`.
4. **Feature Completeness Gate (`min_features_required_ratio`)**:
   - At least 80% of required technical features must be present and non-null.
5. **Abnormal Volatility Gate (`max_rolling_volatility_5d`)**:
   - If rolling 5-session volatility exceeds historical extreme threshold (default: `0.15` or 15% per 5-session period), directional trading is suspended to `HOLD`.
6. **Model Provenance & Cutoff Gate**:
   - The decision timestamp must strictly follow the model's training cutoff date ($T_{\text{decision}} > T_{\text{cutoff}}$). An inverted temporal relationship indicates invalid deployment and triggers `HOLD`.

---

## 7. Transaction Cost and Slippage Model

### 7.1 Component Breakdown
To avoid unrealistic frictionless return claims, transaction costs are explicitly modeled in basis points ($1\text{ bps} = 0.0001$):

| Cost Parameter | Base Assumption (Large-Cap) | Stressed Scenario | Notes |
|---|---|---|---|
| **Entry Brokerage Commission** | 2.5 bps (0.00025) | 5.0 bps | Typical institutional DMA execution fee |
| **Exit Brokerage Commission** | 2.5 bps (0.00025) | 5.0 bps | Typical institutional DMA execution fee |
| **Half Bid-Ask Spread** | 2.5 bps (0.00025) | 7.5 bps | Half-spread for liquid US equities |
| **Execution Slippage (Open/Close)** | 5.0 bps (0.00050) | 12.5 bps | Market impact from entering at open / exiting at close |
| **Total Round-Trip Cost** | **15.0 bps (0.0015)** | **35.0 bps (0.0035)** | Fully deducted from forecast |

### 7.2 Execution Alignment
- **Entry**: Next session $T+1$ open.
- **Exit**: Fifth session $T+5$ close.
- Both entry and exit incur one-way commission, half-spread crossing, and slippage.

---

## 8. API & Dashboard Integration Architecture

1. **New API Endpoint**:
   `POST /api/models/decision`
   - Accepts `DecisionRequest` (ticker, as_of_date, optional cost/risk overrides).
   - Returns typed `DecisionContractResponse`.
2. **Dashboard UI Integration**:
   - Renders a dedicated "Experimental Decision & Risk Card" in the dashboard frontend.
   - Distinctly displays the candidate signal (`BUY` in emerald, `HOLD` in slate/amber, `SELL` in rose).
   - Shows gross forecast, estimated costs, net expected return, active risk checks, and data quality warnings.
   - Strictly preserves existing disclaimer banners and historical backtest labels.
