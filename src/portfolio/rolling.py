"""
Leakage-Safe Rolling Chronological Threshold Selector (Phase 5H).

Performs inner walk-forward / chronological validation strictly within historical training data
to select decision thresholds prior to each outer test window, precluding look-ahead bias and data snooping.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from src.models.baseline import MarketBaselinePipeline
from src.decision.schema import (
    SignalType,
    TransactionCostConfig,
    RiskGateConfig,
    DecisionContractRequest,
)
from src.decision.uncertainty import ResidualUncertaintyEstimator
from src.decision.policy import ThresholdDecisionPolicy
from src.portfolio.schema import RollingThresholdConfig, RollingThresholdResult


class RollingThresholdSelector:
    """
    Selects decision thresholds dynamically per outer fold using strictly prior historical data.
    """

    def __init__(self, config: Optional[RollingThresholdConfig] = None):
        self.config = config or RollingThresholdConfig()

    def select_threshold_for_fold(
        self,
        outer_fold: int,
        df_train_outer: pd.DataFrame,
        feature_columns: List[str],
        base_cost_cfg: TransactionCostConfig,
        max_uncertainty: float = 0.08,
    ) -> RollingThresholdResult:
        """
        Executes inner chronological validation within df_train_outer to select the optimal threshold.

        :param outer_fold: Index of the current outer walk-forward fold.
        :param df_train_outer: Panel DataFrame available strictly prior to outer validation window.
        :param feature_columns: Model feature column names.
        :param base_cost_cfg: Active transaction cost configuration.
        :param max_uncertainty: Risk gate ceiling for forecast residual standard error.
        :return: RollingThresholdResult with selected threshold and full inner audit metadata.
        """
        unique_dates = sorted(df_train_outer["trading_date"].unique().tolist())
        total_dates = len(unique_dates)

        V_inner = self.config.inner_val_sessions
        P_inner = self.config.inner_purge_sessions
        min_required = V_inner + P_inner + 30  # At least 30 sessions for inner training

        if total_dates < min_required:
            return RollingThresholdResult(
                outer_fold=outer_fold,
                selected_threshold=self.config.fallback_threshold,
                fallback_used=True,
                fallback_reason=f"Insufficient historical dates ({total_dates} < {min_required}) for inner validation split.",
                inner_train_dates=f"{unique_dates[0]} to {unique_dates[-1]}",
                inner_val_dates="None",
            )

        # Inner chronological split:
        # Inner Train: [: - (V_inner + P_inner)]
        # Purge Gap: [ - (V_inner + P_inner) : - V_inner]
        # Inner Val: [- V_inner :]
        split_train_end = total_dates - (V_inner + P_inner)
        inner_val_start = total_dates - V_inner

        inner_train_dates = unique_dates[:split_train_end]
        inner_val_dates = unique_dates[inner_val_start:]

        df_inner_train = df_train_outer[df_train_outer["trading_date"].isin(inner_train_dates)].copy()
        df_inner_val = df_train_outer[df_train_outer["trading_date"].isin(inner_val_dates)].copy()

        y_inner_tr = df_inner_train["target_forward_return_5d"].values
        y_inner_val = df_inner_val["target_forward_return_5d"].values

        # 1. Fit Ridge pipeline strictly on inner training set
        pipeline = MarketBaselinePipeline(feature_columns=feature_columns)
        fit_res = pipeline.fit_and_evaluate_ridge(
            df_inner_train, y_inner_tr, df_inner_val, y_inner_val, model_name=f"InnerRidge_Fold{outer_fold}"
        )

        # 2. Derive training residuals for uncertainty estimation
        pipeline_tr = MarketBaselinePipeline(
            feature_columns=feature_columns, alphas=(fit_res.best_params["alpha"],)
        )
        res_tr_eval = pipeline_tr.fit_and_evaluate_ridge(
            df_inner_train, y_inner_tr, df_inner_train, y_inner_tr, model_name="InnerTrainOnly"
        )
        inner_train_resids = y_inner_tr - res_tr_eval.predictions
        uncertainty_estimator = ResidualUncertaintyEstimator(
            training_residuals=inner_train_resids, method_name="inner_train_residual_std"
        )
        sigma_inner = uncertainty_estimator.get_uncertainty()

        inner_preds = fit_res.predictions
        cost_dec = base_cost_cfg.total_roundtrip_decimal

        # 3. Evaluate each candidate threshold on inner validation set
        threshold_metrics: Dict[float, Dict[str, Any]] = {}
        trade_counts: Dict[str, int] = {}
        net_returns: Dict[str, float] = {}

        for th in self.config.candidate_thresholds:
            policy = ThresholdDecisionPolicy(uncertainty_estimator=uncertainty_estimator)
            risk_cfg = RiskGateConfig(
                buy_threshold=th,
                sell_threshold=-th,
                max_uncertainty=max_uncertainty,
                min_net_return_hurdle=0.005,
                enforce_uncertainty_gate=True,
            )

            active_returns: List[float] = []
            trade_count = 0

            for j in range(len(df_inner_val)):
                row = df_inner_val.iloc[j]
                pred = inner_preds[j]
                y_act = y_inner_val[j]
                vol_5d = row.get("market_volatility_5d")

                req = DecisionContractRequest(
                    company_id=row["company_id"],
                    ticker=row["ticker"],
                    decision_timestamp=f"{row['trading_date']}T14:15:00Z",
                    predicted_forward_return=pred,
                    forecast_uncertainty=sigma_inner,
                    rolling_volatility_5d=float(vol_5d) if pd.notna(vol_5d) else None,
                    feature_metadata={"n_features_used": len(feature_columns), "n_features_required": len(feature_columns)},
                    model_id=f"InnerRidge_Fold{outer_fold}",
                    training_cutoff_date=inner_train_dates[-1],
                    cost_config=base_cost_cfg,
                    risk_config=risk_cfg,
                )

                resp = policy.evaluate(req)
                if resp.signal == SignalType.BUY:
                    net_ret = y_act - cost_dec
                    active_returns.append(net_ret)
                    trade_count += 1
                elif resp.signal == SignalType.SELL:
                    net_ret = -y_act - cost_dec
                    active_returns.append(net_ret)
                    trade_count += 1

            mean_net = float(np.mean(active_returns)) if active_returns else 0.0
            win_rate = float(np.mean(np.array(active_returns) > 0)) if active_returns else 0.0

            threshold_metrics[th] = {
                "trade_count": trade_count,
                "mean_net_return": mean_net,
                "win_rate": win_rate,
            }
            trade_counts[f"{th*100:.1f}%"] = trade_count
            net_returns[f"{th*100:.1f}%"] = mean_net

        # 4. Selection Logic
        # Filter candidate thresholds that meet minimum trade count requirement
        qualifying = [
            (th, metrics)
            for th, metrics in threshold_metrics.items()
            if metrics["trade_count"] >= self.config.min_inner_trades and metrics["win_rate"] >= 0.50
        ]

        if not qualifying:
            # Fallback triggered when inner evidence is sparse or unprofitable
            return RollingThresholdResult(
                outer_fold=outer_fold,
                selected_threshold=self.config.fallback_threshold,
                fallback_used=True,
                fallback_reason=f"Sparse inner validation evidence: No candidate threshold produced >= {self.config.min_inner_trades} active trades with >= 50% win rate.",
                inner_val_trade_counts=trade_counts,
                inner_val_net_returns=net_returns,
                inner_train_dates=f"{inner_train_dates[0]} to {inner_train_dates[-1]} (N={len(inner_train_dates)})",
                inner_val_dates=f"{inner_val_dates[0]} to {inner_val_dates[-1]} (N={len(inner_val_dates)})",
            )

        # Sort qualifying by highest mean_net_return, tie-break by lower threshold for stability
        qualifying.sort(key=lambda x: (x[1]["mean_net_return"], -x[0]), reverse=True)
        best_th, best_metrics = qualifying[0]

        return RollingThresholdResult(
            outer_fold=outer_fold,
            selected_threshold=float(best_th),
            fallback_used=False,
            fallback_reason=None,
            inner_val_trade_counts=trade_counts,
            inner_val_net_returns=net_returns,
            inner_train_dates=f"{inner_train_dates[0]} to {inner_train_dates[-1]} (N={len(inner_train_dates)})",
            inner_val_dates=f"{inner_val_dates[0]} to {inner_val_dates[-1]} (N={len(inner_val_dates)})",
        )
