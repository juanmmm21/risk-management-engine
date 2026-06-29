from __future__ import annotations

from typing import Protocol

from risk_management_engine.models import (
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskViolation,
)


class RiskRule(Protocol):
    """Regla atómica de validación pre-trade."""

    rule_id: str

    def evaluate(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
        config: RiskLimitsConfig,
    ) -> list[RiskViolation]:
        ...


class PreTradeRiskGate(Protocol):
    def check_order(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
    ) -> object:
        ...
