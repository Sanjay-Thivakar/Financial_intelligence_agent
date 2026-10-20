# Phase 5H — Portfolio Simulation & Leakage-Safe Threshold Validation Specification

**Phase**: 5H  
**Component**: Portfolio Simulation & Rolling Threshold Validation  
**Status**: Architecture & Design Specification  
**Date**: October 2026  
**Disclaimer**: This document specifies a research portfolio-simulation and risk-accounting engine. It does **not** constitute personalized investment advice, trading recommendations, or a guarantee of profitability.

---

## 1. System Objective & Research Context

Phase 5G established the Decision & Risk Layer, which converts statistical model forward-return forecasts into experimental `BUY`, `HOLD`, and `SELL` candidate signals. However, Phase 5G.1 identified four fundamental limitations:
1. **Unmodeled Overlapping Exposures**: 5-session forward return targets overlap daily. Evaluating every daily signal as an independent, fully funded trade ignores concurrent portfolio capacity and over-concentrates capital in single assets.
2. **Denominators & Metric Comparability**: Averaging returns across 720 observations (including 713 idle cash periods) yields an opportunity-diluted $+0.03\%$ per-session return, whereas active trades achieved $+3.13\%$.
3. **Exploratory Threshold Selection**: The $1.0\% - 1.5\%$ threshold grid was evaluated in-sample across the entire 720-observation evaluation period, introducing selection bias.
4. **Capital & Execution Realism**: Cash drag, capital conservation, and concurrent position caps were unmodeled.

The objective of **Phase 5H** is to resolve these limitations by constructing:
1. A **Deterministic Portfolio Simulator** that models multi-asset capital allocation, concurrent position tracking, non-overlapping holding constraints, and exact transaction friction accounting.
2. A **Leakage-Safe Rolling Chronological Threshold Selector** that dynamically tunes decision thresholds strictly within historical training partitions before each outer test fold.

---

## 2. Invariants & Research Boundaries

1. **Target Invariant**:
   - Decision at session $T$ close / next session pre-open cutoff ($09:15$ ET).
   - Trade entry at session $T+1$ open ($P_{T+1,\text{open}}$).
   - Trade exit at session $T+5$ close ($P_{T+5,\text{close}}$).
   - Fixed 5-trading-session holding horizon ($H = 5$).
2. **Temporal Integrity**:
   - Zero look-ahead bias: No future market or event information may influence decisions or portfolio constraints at time $T$.
   - Preprocessing and uncertainty estimation use training partitions strictly prior to the evaluation window.
   - Threshold selection for outer fold $k$ uses only historical data $D_{\text{train}, k}$, enforced via inner chronological validation and purge gaps.
3. **Long-Only Research Scope**:
   - `BUY`: Evaluated for long equity position entry.
   - `HOLD`: Neutral, creates no position.
   - `SELL`: Documented as neutral / non-trading. Short selling, borrow fees, and margin lending are unmodeled and excluded.
   - No leverage: Aggregate portfolio exposure capped at $100\%$ ($\le 1.0$).
4. **Cohort Integrity**:
   - 4 verified companies: `AAPL`, `JPM`, `GOOG`, `TSLA`.
   - Excluded ticker `AA` remains barred.

---

## 3. Portfolio Simulation Architecture

The simulation engine is implemented in `src/portfolio/simulator.py` and structured around `DeterministicPortfolioSimulator`.

### 3.1 State and Accounting Variables

At any session $t$, the portfolio is defined by:
- **Cash ($C_t$)**: Uninvested liquid currency in USD.
- **Invested Capital ($I_t$)**: Current market value of all open equity positions:
  $$I_t = \sum_{p \in \mathcal{P}_{\text{open}}} S_p \cdot P_{t,\text{close}}$$
- **Portfolio Equity ($E_t$)**: Total net liquidating value:
  $$E_t = C_t + I_t$$
- **Conservation of Capital Invariant**:
  $$E_t = E_0 + \sum \text{Realized PnL} + \sum \text{Unrealized PnL} - \sum \text{Transaction Costs}$$

### 3.2 Configurable Portfolio Constraints

Defined in `src/portfolio/schema.py` under `PortfolioConfig`:
- `initial_cash`: $\$100,000.00$ default starting capital.
- `max_concurrent_positions`: $4$ simultaneous open positions.
- `max_position_weight`: $0.25$ ($25\%$ maximum target allocation per trade).
- `max_aggregate_exposure`: $1.0$ ($100\%$ maximum invested capital, zero leverage).
- `min_cash_reserve`: $\$0.00$ minimum liquidity buffer.
- `min_order_amount`: $\$100.00$ order threshold to avoid trivial fractional sizing.
- `allow_multiple_positions_per_ticker`: `False` (prevents stacking multiple overlapping positions in the exact same asset).
- `cost_config`: Reusable `TransactionCostConfig` modeling institutional fees, spread, and slippage.

### 3.3 Position Lifecycle State Machine

```
[Candidate Signal at Session T Close]
                 │
                 ▼
      [Constraint Evaluation]
     ┌───────────┴───────────┐
   Pass                     Fail
     │                       │
     ▼                       ▼
[PENDING_ENTRY]        [REJECTED]
(Capital Reserved)     (Reason Logged: CONCURRENT_LIMIT,
     │                  MAX_TICKER, INSUFFICIENT_CASH, etc.)
     ▼ (At Session T+1 Open)
   [OPEN]
(Entry Price Paid, Entry Cost Deducted, Shares Issued)
     │
     ▼ (Sessions T+1 through T+4 Close)
[MARK-TO-MARKET]
(Unrealized PnL Computed Daily)
     │
     ▼ (At Session T+5 Close)
  [CLOSED]
(Shares Sold at Exit Price, Exit Cost Deducted,
 Cash Credited, Realized PnL Calculated, Capital Released)
```

---

## 4. Leakage-Safe Rolling Threshold Selection Protocol

### 4.1 Chronological Partitioning

For each outer walk-forward fold $k \in \{0, 1, 2, 3\}$:
- The outer test period $V_k$ consists of 45 trading sessions (180 observation rows).
- The historical dataset $D_{\text{train}, k}$ available prior to $V_k$ is partitioned into:
  - **Inner Train**: Sessions $[0 \dots N - (V_{\text{inner}} + P_{\text{inner}})]$.
  - **Inner Purge Gap**: $P_{\text{inner}} = 5$ sessions to eliminate label overlap.
  - **Inner Validation**: $V_{\text{inner}} = 45$ sessions immediately preceding outer fold $k$.

### 4.2 Candidate Threshold Grid & Optimization Objective

- Candidate grid: $\theta \in [0.005, 0.010, 0.015, 0.020, 0.030]$ ($0.5\%, 1.0\%, 1.5\%, 2.0\%, 3.0\%$).
- Model training: Ridge regression ($\alpha = 1000.0$) is trained strictly on Inner Train; training residuals calibrate $\sigma_{\text{inner}}$.
- Evaluation: Each candidate $\theta$ is evaluated out-of-sample on Inner Validation under full Decision & Risk Layer gates.
- Selection Objective:
  $$\theta^* = \arg\max_{\theta} \left\{ \text{Mean Net Return}(\theta) \;\middle|\; N_{\text{trades}}(\theta) \ge 3 \text{ and } \text{Win Rate}(\theta) \ge 50\% \right\}$$
- Tie-breaking: If returns tie, select the lower threshold for stability.
- **Conservative Fallback Rule**:
  If no candidate threshold yields at least 3 trades with $\ge 50\%$ win rate on Inner Validation:
  $$\theta^* = \theta_{\text{fallback}} = 0.015 \quad (1.5\%)$$
  The selector marks `fallback_used = True` and logs the exact diagnostic reason in the evaluation metadata.

---

## 5. Transaction Cost and Slippage Accounting

Costs are deducted at both transaction boundaries:
- **Entry Friction**:
  $$\text{Entry Cost} = S \cdot P_{T+1,\text{open}} \cdot \frac{\text{Entry Fee} + \text{Half Spread} + \text{Slippage}}{10000}$$
- **Exit Friction**:
  $$\text{Exit Cost} = S \cdot P_{T+5,\text{close}} \cdot \frac{\text{Exit Fee} + \text{Half Spread} + \text{Slippage}}{10000}$$
- **Base Round-Trip Parameter**: $15.0\text{ bps}$ ($0.00150$), composed of $2.5\text{ bps}$ entry, $2.5\text{ bps}$ exit, $5.0\text{ bps}$ total spread crossing, and $5.0\text{ bps}$ total slippage.
- Friction is fully integrated into cash balances and realized profit/loss:
  $$\text{Realized PnL} = (S \cdot P_{\text{exit}} - \text{Exit Cost}) - (S \cdot P_{\text{entry}} + \text{Entry Cost})$$

---

## 6. Evaluation Strategy Baselines

All strategies are evaluated across the exact same calendar sessions and price history:
1. **Baseline 1: Cash Benchmark**: 100% Cash ($E_T = \$100,000.00$, zero trades, zero return, zero drawdown).
2. **Baseline 2: Equal-Weight Buy & Hold**: 25% allocated to `AAPL`, `JPM`, `GOOG`, `TSLA` at the start of the evaluation window, held across the full period.
3. **Strategy 1: Phase 5G Fixed Policy ($1.5\%$)**: Base risk gates and fixed $1.5\%$ threshold executed through the deterministic portfolio simulator.
4. **Strategy 2: Phase 5H Rolling Threshold Policy**: Inner-validated rolling threshold selected per fold, executed through the deterministic portfolio simulator.
