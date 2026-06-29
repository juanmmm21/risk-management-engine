from __future__ import annotations

import logging

from risk_management_engine.models import (
    PortfolioSnapshot,
    ProposedOrder,
    RiskCheckResult,
    RiskLimitsConfig,
    RiskVerdict,
    RiskViolation,
    RiskViolationType,
)
from risk_management_engine.protocols import RiskRule
from risk_management_engine.rules import DrawdownRule, PositionSizingRule, StopLossRule

logger = logging.getLogger(__name__)


class RiskManagementEngine:
    """Orquestador determinista de reglas pre-trade."""

    def __init__(
        self,
        config: RiskLimitsConfig,
        rules: list[RiskRule] | None = None,
    ) -> None:
        self._config = config
        self._rules = rules or [
            DrawdownRule(),
            PositionSizingRule(),
            StopLossRule(),
        ]

    @property
    def config(self) -> RiskLimitsConfig:
        return self._config

    def check_order(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
    ) -> RiskCheckResult:
        if order.symbol != portfolio.symbol:
            raise ValueError("order symbol must match portfolio snapshot symbol")

        violations = self._collect_violations(order, portfolio)
        verdict = RiskVerdict.REJECTED if violations else RiskVerdict.APPROVED

        result = RiskCheckResult(
            client_order_id=order.client_order_id,
            verdict=verdict,
            violations=tuple(violations),
            evaluated_at=order.submitted_at,
            order_notional=order.notional,
            equity=portfolio.equity,
        )
        logger.info(
            "risk check client_order_id=%s verdict=%s violations=%s",
            order.client_order_id,
            verdict.value,
            len(violations),
        )
        return result

    def _collect_violations(
        self,
        order: ProposedOrder,
        portfolio: PortfolioSnapshot,
    ) -> list[RiskViolation]:
        violations: list[RiskViolation] = []
        for rule in self._rules:
            try:
                rule_violations = rule.evaluate(order, portfolio, self._config)
            except Exception as exc:
                logger.exception("rule %s failed for order %s", rule.rule_id, order.client_order_id)
                violations.append(
                    RiskViolation(
                        rule_id=rule.rule_id,
                        violation_type=RiskViolationType.RULE_EVALUATION_ERROR,
                        message=f"rule evaluation error: {exc}",
                    )
                )
                continue
            violations.extend(rule_violations)
        return violations
