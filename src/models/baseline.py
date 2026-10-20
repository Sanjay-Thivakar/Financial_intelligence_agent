"""
Market Baseline Model and Reference Benchmarks.

Provides:
- Reference 0: Naive Zero-Return Benchmark (predicts 0.0).
- Reference 1: Historical Median Return Benchmark (predicts train median).
- Model 1: Market-Only Ridge Regression with cross-validated alpha selection.

Strict Invariants:
- Imputation and feature scaling are fit strictly on training data.
- Hyperparameter search uses internal walk-forward validation on train folds.
- Metrics computed: RMSE, MAE, Hit Rate (Directional Accuracy), and Information Coefficient (Spearman Rank Correlation).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import logging
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

logger = logging.getLogger(__name__)


@dataclass
class BaselineEvaluationResult:
    """Artifact containing evaluation metrics and performance comparisons."""
    model_name: str
    rmse: float
    mae: float
    hit_rate: float
    information_coefficient: float
    ic_pvalue: float
    n_samples: int
    predictions: np.ndarray
    actuals: np.ndarray
    best_params: Dict[str, Any] = field(default_factory=dict)


class MarketBaselinePipeline:
    """Pipelines and evaluates predictive models under strict temporal isolation."""

    MARKET_FEATURE_COLUMNS = [
        "market_return_1d",
        "market_return_5d",
        "market_return_21d",
        "market_log_return_1d",
        "market_volatility_5d",
        "market_volatility_21d",
        "market_volatility_63d",
        "market_momentum_5d",
        "market_momentum_21d",
        "market_momentum_63d",
        "market_sma_20d",
        "market_sma_50d",
        "market_zscore_20d",
        "market_zscore_50d",
        "market_rsi_14d",
        "market_volume_change_1d",
        "market_volume_ratio_20d",
    ]
    # Retain FEATURE_COLUMNS for backwards compatibility
    FEATURE_COLUMNS = MARKET_FEATURE_COLUMNS

    FUNDAMENTAL_FEATURE_COLUMNS = [
        "fundamental_ratio_net_margin",
        "fundamental_ratio_roa",
        "fundamental_ratio_debt_to_assets",
        "fundamental_ratio_debt_to_equity",
        "fundamental_ratio_ocf_to_net_income",
        "fundamental_diluted_eps",
        "fundamental_revenue_age_days",
        "fundamental_all_facts_stale",
    ]

    COMBINED_FEATURE_COLUMNS = MARKET_FEATURE_COLUMNS + FUNDAMENTAL_FEATURE_COLUMNS

    EVENT_FEATURE_COLUMNS = [
        "sec_event_count_5d",
        "sec_earnings_release_in_window",
        "sec_days_since_last_8k",
    ]

    MARKET_PLUS_EVENT_COLUMNS = MARKET_FEATURE_COLUMNS + EVENT_FEATURE_COLUMNS
    ALL_FEATURE_COLUMNS = MARKET_FEATURE_COLUMNS + FUNDAMENTAL_FEATURE_COLUMNS + EVENT_FEATURE_COLUMNS

    def __init__(
        self,
        alphas: Tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0),
        feature_columns: Optional[List[str]] = None,
    ):
        self.alphas = alphas
        self.feature_columns = feature_columns or self.FEATURE_COLUMNS

    def evaluate_naive_zero(self, y_true: np.ndarray) -> BaselineEvaluationResult:
        """Evaluates Reference 0: Naive Zero Return."""
        y_pred = np.zeros_like(y_true)
        return self._compute_metrics("Reference 0 (Zero Return)", y_true, y_pred)

    def evaluate_naive_median(self, y_train: np.ndarray, y_val: np.ndarray) -> BaselineEvaluationResult:
        """Evaluates Reference 1: Historical Median Return from Training Set."""
        med_val = float(np.median(y_train))
        y_pred = np.full_like(y_val, fill_value=med_val)
        return self._compute_metrics("Reference 1 (Historical Median)", y_val, y_pred)

    def fit_and_evaluate_ridge(
        self,
        X_train: pd.DataFrame,
        y_train: np.ndarray,
        X_val: pd.DataFrame,
        y_val: np.ndarray,
        model_name: str = "Model 1 (Market-Only Ridge)",
        date_column: str = "trading_date",
    ) -> BaselineEvaluationResult:
        """
        Fits Ridge regression with strict training-only preprocessing and hyperparameter selection.
        Enforces:
        - Internal chronological splits on unique trading dates (keeping all companies on each date grouped).
        - Strictly isolated internal preprocessing during alpha tuning (zero leakage from internal validation).
        - Final outer refit of preprocessing and Ridge model on the complete outer training fold.
        """
        cols = [c for c in self.feature_columns if c in X_train.columns and X_train[c].notna().any()]
        if not cols:
            raise ValueError(f"None of the required feature columns {self.feature_columns} found in X_train.")

        # 1. Determine internal chronological split for hyperparameter tuning
        n_train = len(X_train)
        has_dates = date_column in X_train.columns and X_train[date_column].notna().any()

        if has_dates:
            # Group by unique trading dates to keep all companies from any given date together
            unique_dates = pd.Series(X_train[date_column].unique())
            n_dates = len(unique_dates)
            if n_dates >= 10:
                split_date_idx = int(n_dates * 0.7)
                inner_tr_dates = set(unique_dates.iloc[:split_date_idx])
                inner_val_dates = set(unique_dates.iloc[split_date_idx:])
                inner_tr_mask = X_train[date_column].isin(inner_tr_dates).to_numpy()
                inner_val_mask = X_train[date_column].isin(inner_val_dates).to_numpy()
            elif n_train >= 20:
                split_idx = int(n_train * 0.7)
                inner_tr_mask = np.zeros(n_train, dtype=bool)
                inner_tr_mask[:split_idx] = True
                inner_val_mask = ~inner_tr_mask
            else:
                inner_tr_mask, inner_val_mask = None, None
        elif n_train >= 20:
            split_idx = int(n_train * 0.7)
            inner_tr_mask = np.zeros(n_train, dtype=bool)
            inner_tr_mask[:split_idx] = True
            inner_val_mask = ~inner_tr_mask
        else:
            inner_tr_mask, inner_val_mask = None, None

        # 2. Alpha tuning via strictly isolated internal validation
        best_alpha = self.alphas[0]
        if inner_tr_mask is not None and inner_val_mask is not None and inner_tr_mask.sum() > 0 and inner_val_mask.sum() > 0:
            best_val_rmse = float("inf")

            # Fit imputer and scaler strictly on inner training split
            inner_imputer = SimpleImputer(strategy="median")
            inner_X_tr_imp = inner_imputer.fit_transform(X_train.loc[inner_tr_mask, cols])
            inner_X_va_imp = inner_imputer.transform(X_train.loc[inner_val_mask, cols])

            inner_scaler = StandardScaler()
            inner_X_tr_scaled = inner_scaler.fit_transform(inner_X_tr_imp)
            inner_X_va_scaled = inner_scaler.transform(inner_X_va_imp)

            inner_y_tr = y_train[inner_tr_mask]
            inner_y_va = y_train[inner_val_mask]

            for a in self.alphas:
                m = Ridge(alpha=a, random_state=42)
                m.fit(inner_X_tr_scaled, inner_y_tr)
                preds = m.predict(inner_X_va_scaled)
                rmse = np.sqrt(np.mean((inner_y_va - preds) ** 2))
                if rmse < best_val_rmse:
                    best_val_rmse = rmse
                    best_alpha = a
        else:
            best_alpha = 10.0  # Conservative default regularization for small sets

        # 3. Outer Refit: Fit imputer and scaler on the complete outer training fold
        outer_imputer = SimpleImputer(strategy="median")
        X_train_imp = outer_imputer.fit_transform(X_train[cols])
        X_val_imp = outer_imputer.transform(X_val[cols])

        outer_scaler = StandardScaler()
        X_train_scaled = outer_scaler.fit_transform(X_train_imp)
        X_val_scaled = outer_scaler.transform(X_val_imp)

        final_model = Ridge(alpha=best_alpha, random_state=42)
        final_model.fit(X_train_scaled, y_train)

        # 4. Predict on outer validation fold
        y_pred = final_model.predict(X_val_scaled)

        result = self._compute_metrics(model_name, y_val, y_pred)
        result.best_params = {"alpha": best_alpha, "features_used": len(cols)}
        return result

    def _compute_metrics(self, name: str, y_true: np.ndarray, y_pred: np.ndarray) -> BaselineEvaluationResult:
        """Computes standardized predictive evaluation metrics."""
        err = y_true - y_pred
        rmse = float(np.sqrt(np.mean(err ** 2)))
        mae = float(np.mean(np.abs(err)))

        # Directional Accuracy (Hit Rate): sign agreement (excluding exact 0)
        valid_signs = (y_true != 0) & (y_pred != 0)
        if valid_signs.any():
            hit_rate = float(np.mean(np.sign(y_true[valid_signs]) == np.sign(y_pred[valid_signs])))
        else:
            hit_rate = 0.5  # Neutral default

        # Information Coefficient: Spearman rank correlation
        # NOTE ON INFERENCE: Because forward-return target labels overlap by H-1 sessions,
        # ordinary Spearman p-values assume independent observations and are not valid
        # for statistical significance testing without Newey-West or Hansen-Hodrick corrections.
        # This IC p-value is descriptive/exploratory only and must not be used for inferential claims.
        if len(y_true) >= 3 and not (np.all(y_pred == y_pred[0]) or np.all(y_true == y_true[0])):
            ic, p_val = spearmanr(y_pred, y_true)
            ic = float(ic) if not np.isnan(ic) else 0.0
            p_val = float(p_val) if not np.isnan(p_val) else 1.0
        else:
            ic, p_val = 0.0, 1.0

        return BaselineEvaluationResult(
            model_name=name,
            rmse=rmse,
            mae=mae,
            hit_rate=hit_rate,
            information_coefficient=ic,
            ic_pvalue=p_val,
            n_samples=len(y_true),
            predictions=y_pred,
            actuals=y_true,
        )


# Module-level aliases for convenience
MARKET_FEATURE_COLUMNS = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
FUNDAMENTAL_FEATURE_COLUMNS = MarketBaselinePipeline.FUNDAMENTAL_FEATURE_COLUMNS
COMBINED_FEATURE_COLUMNS = MarketBaselinePipeline.COMBINED_FEATURE_COLUMNS
EVENT_FEATURE_COLUMNS = MarketBaselinePipeline.EVENT_FEATURE_COLUMNS
MARKET_PLUS_EVENT_COLUMNS = MarketBaselinePipeline.MARKET_PLUS_EVENT_COLUMNS
ALL_FEATURE_COLUMNS = MarketBaselinePipeline.ALL_FEATURE_COLUMNS
