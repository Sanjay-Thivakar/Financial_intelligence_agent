"""
Forecast Uncertainty Estimation (Phase 5G).

Computes defensible predictive uncertainty intervals strictly using historical
training or validation residuals, preventing future leakage into live decisions.
"""

from typing import Optional, Tuple, Dict, Any
import numpy as np


class ResidualUncertaintyEstimator:
    """
    Estimates predictive uncertainty from in-sample or cross-validated historical residuals.
    """

    def __init__(
        self,
        training_residuals: Optional[np.ndarray] = None,
        residual_std: Optional[float] = None,
        method_name: str = "training_residual_std",
    ):
        """
        :param training_residuals: Array of historical (actual - predicted) errors from training folds only.
        :param residual_std: Pre-computed residual standard deviation.
        :param method_name: Documentation label for audit tracking.
        """
        self.method_name = method_name
        if residual_std is not None and residual_std > 0:
            self.residual_std = float(residual_std)
            self.n_samples = 0
        elif training_residuals is not None and len(training_residuals) >= 10:
            valid_resids = training_residuals[np.isfinite(training_residuals)]
            self.n_samples = len(valid_resids)
            self.residual_std = float(np.std(valid_resids, ddof=1)) if self.n_samples > 1 else None
        else:
            self.residual_std = None
            self.n_samples = 0

    @property
    def is_available(self) -> bool:
        """Returns True if a valid uncertainty estimate has been calibrated."""
        return self.residual_std is not None and np.isfinite(self.residual_std) and self.residual_std > 0

    def get_uncertainty(self) -> Optional[float]:
        """Returns calibrated residual standard deviation (uncertainty metric)."""
        return self.residual_std if self.is_available else None

    def compute_prediction_interval(
        self,
        predicted_return: float,
        confidence_level: float = 0.80,
    ) -> Optional[Tuple[float, float]]:
        """
        Computes a symmetric prediction interval around the forecast:
        [y_hat - z * sigma, y_hat + z * sigma].
        Common z-values: 80% -> 1.282, 90% -> 1.645, 95% -> 1.960.
        """
        if not self.is_available:
            return None

        # Standard normal quantiles
        z_scores = {
            0.80: 1.28155,
            0.90: 1.64485,
            0.95: 1.95996,
        }
        z = z_scores.get(confidence_level, 1.28155)
        margin = z * self.residual_std
        return (predicted_return - margin, predicted_return + margin)

    def to_metadata(self) -> Dict[str, Any]:
        """Provides metadata for response audit and logging."""
        return {
            "is_available": self.is_available,
            "method": self.method_name,
            "residual_std": self.residual_std,
            "n_calibration_samples": self.n_samples,
        }
