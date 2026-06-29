from __future__ import annotations

from risk_management_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskViolation,
    RiskViolationType,
)


class PositionSizingRule:
    rule_id = "position_sizing"

    def evaluate(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
        config: RiskLimitsConfig,
    ) -> list[RiskViolation]:
        violations: list[RiskViolation] = []
        order_notional = order.notional
        max_order_notional = portfolio.equity * config.max_order_notional_pct

        if order_notional > max_order_notional:
            violations.append(
                RiskViolation(
                    rule_id=self.rule_id,
                    violation_type=RiskViolationType.ORDER_NOTIONAL_EXCEEDED,
                    message=(
                        f"order notional {order_notional} exceeds limit "
                        f"{max_order_notional} ({config.max_order_notional_pct:.2%} of equity)"
                    ),
                )
            )

        if order.side is not OrderSide.BUY:
            return violations

        projected_quantity = portfolio.position_quantity + order.quantity
        projected_notional = projected_quantity * order.reference_price
        max_position_notional = portfolio.equity * config.max_position_notional_pct

        if projected_notional > max_position_notional:
            violations.append(
                RiskViolation(
                    rule_id=self.rule_id,
                    violation_type=RiskViolationType.POSITION_SIZE_EXCEEDED,
                    message=(
                        "projected position notional "
                        f"{projected_notional} exceeds limit {max_position_notional}"
                    ),
                )
            )

        if order_notional > portfolio.cash:
            violations.append(
                RiskViolation(
                    rule_id=self.rule_id,
                    violation_type=RiskViolationType.INSUFFICIENT_CAPITAL,
                    message=(
                        f"order notional {order_notional} exceeds available cash "
                        f"{portfolio.cash}"
                    ),
                )
            )

        return violations
