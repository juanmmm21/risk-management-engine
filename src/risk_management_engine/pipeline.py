from __future__ import annotations

from typing import Any

from risk_management_engine.engine import RiskManagementEngine
from risk_management_engine.ingest import load_orders, load_portfolio_snapshot
from risk_management_engine.models import RiskCheckResult, RiskLimitsConfig


def serialize_risk_result(result: RiskCheckResult) -> dict[str, Any]:
    return {
        "client_order_id": result.client_order_id,
        "verdict": result.verdict.value,
        "evaluated_at": result.evaluated_at.isoformat(),
        "order_notional": str(result.order_notional),
        "equity": str(result.equity),
        "violations": [
            {
                "rule_id": violation.rule_id,
                "violation_type": violation.violation_type.value,
                "message": violation.message,
            }
            for violation in result.violations
        ],
    }


def run_risk_check_pipeline(
    orders_path: str,
    portfolio_path: str,
    symbol: str,
    config: RiskLimitsConfig,
) -> list[dict[str, Any]]:
    orders = load_orders(orders_path, default_symbol=symbol)
    portfolio = load_portfolio_snapshot(portfolio_path, default_symbol=symbol)
    engine = RiskManagementEngine(config)

    results: list[dict[str, Any]] = []
    for order in orders:
        if order.symbol != symbol:
            continue
        check = engine.check_order(order, portfolio)
        results.append(serialize_risk_result(check))
    return results
