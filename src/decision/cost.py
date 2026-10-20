"""
Transaction Cost and Execution Slippage Model (Phase 5G).

Models institutional trading friction for 5-session forward return targets:
- Entry at session T+1 open
- Exit at session T+5 close
- Entry and exit brokerage commissions
- Half bid-ask spread crossing
- Execution market impact / slippage
"""

from typing import Dict, Any
from src.decision.schema import TransactionCostConfig, SignalType


class TransactionCostModel:
    """
    Computes realistic transaction cost deductions aligned with execution conventions.
    """

    @staticmethod
    def calculate_roundtrip_cost(config: TransactionCostConfig) -> float:
        """
        Calculates total round-trip friction as a decimal return deduction.
        Example: 15 bps = 0.0015.
        """
        return config.total_roundtrip_decimal

    @staticmethod
    def calculate_cost_breakdown(config: TransactionCostConfig) -> Dict[str, float]:
        """Provides an itemized breakdown of cost components in basis points."""
        return {
            "entry_commission_bps": config.entry_fee_bps,
            "exit_commission_bps": config.exit_fee_bps,
            "total_spread_bps": 2.0 * config.half_spread_bps,
            "total_slippage_bps": 2.0 * config.slippage_bps,
            "total_roundtrip_bps": config.total_roundtrip_bps,
            "total_roundtrip_decimal": config.total_roundtrip_decimal,
        }

    @staticmethod
    def calculate_expected_net_return(
        predicted_return: float,
        candidate_direction: SignalType,
        config: TransactionCostConfig,
    ) -> float:
        """
        Adjusts raw predicted return for execution friction:
        - For a candidate BUY (long): Net Return = Forecast Return - Round-Trip Cost
        - For a candidate SELL (short): Net Return = Forecast Return + Round-Trip Cost (less negative / worse)
        - For HOLD: Net Return = Forecast Return
        """
        roundtrip = config.total_roundtrip_decimal
        if candidate_direction == SignalType.BUY:
            return predicted_return - roundtrip
        elif candidate_direction == SignalType.SELL:
            # If predicting -0.03 (-3%), cost of 0.0015 increases required magnitude:
            # expected net short return = (-predicted_return) - roundtrip = 0.03 - 0.0015 = +0.0285.
            # In raw return space: predicted_return + roundtrip = -0.03 + 0.0015 = -0.0285.
            return predicted_return + roundtrip
        else:
            return predicted_return
