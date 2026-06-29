from __future__ import annotations

from risk_management_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskViolation,
    RiskViolationType,
)


class DrawdownRule:
    rule_id = "drawdown"

    def evaluate(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
        config: RiskLimitsConfig,
    ) -> list[RiskViolation]:
        drawdown_pct = portfolio.daily_drawdown_pct
        if drawdown_pct < config.max_daily_drawdown_pct:
            return []

        if order.side is OrderSide.SELL:
            return []

        return [
            RiskViolation(
                rule_id=self.rule_id,
                violation_type=RiskViolationType.MAX_DRAWDOWN_EXCEEDED,
                message=(
                    f"daily drawdown {drawdown_pct:.2%} reached limit "
                    f"{config.max_daily_drawdown_pct:.2%}; blocking new risk-increasing orders"
                ),
            )
        ]
