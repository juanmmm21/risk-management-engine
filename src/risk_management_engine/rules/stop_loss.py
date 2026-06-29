from __future__ import annotations

from decimal import Decimal

from risk_management_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskViolation,
    RiskViolationType,
)


class StopLossRule:
    rule_id = "stop_loss"

    def evaluate(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
        config: RiskLimitsConfig,
    ) -> list[RiskViolation]:
        if not config.require_stop_loss_on_entry:
            return []
        if order.side is not OrderSide.BUY:
            return []
        if portfolio.position_quantity > Decimal("0"):
            return []

        if order.stop_loss_price is None:
            return [
                RiskViolation(
                    rule_id=self.rule_id,
                    violation_type=RiskViolationType.MISSING_STOP_LOSS,
                    message="stop_loss_price is required for new long entries",
                )
            ]

        if order.stop_loss_price >= order.reference_price:
            return [
                RiskViolation(
                    rule_id=self.rule_id,
                    violation_type=RiskViolationType.INVALID_STOP_LOSS,
                    message="stop_loss_price must be below reference_price for long entries",
                )
            ]

        distance_pct = (order.reference_price - order.stop_loss_price) / order.reference_price
        if distance_pct < config.min_stop_loss_distance_pct:
            return [
                RiskViolation(
                    rule_id=self.rule_id,
                    violation_type=RiskViolationType.INVALID_STOP_LOSS,
                    message=(
                        f"stop loss distance {distance_pct:.4%} is below minimum "
                        f"{config.min_stop_loss_distance_pct:.4%}"
                    ),
                )
            ]

        return []
