from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from risk_management_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskViolationType,
)
from risk_management_engine.rules.position_sizing import PositionSizingRule


def _portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        symbol="BTCUSDT",
        cash=Decimal("9500"),
        equity=Decimal("10000"),
        position_quantity=Decimal("0"),
        average_entry_price=Decimal("0"),
        daily_realized_pnl=Decimal("0"),
        peak_equity_today=Decimal("10000"),
        snapshot_time=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _order(quantity: str = "0.01") -> ProposedOrder:
    return ProposedOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        reference_price=Decimal("1000"),
        submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        stop_loss_price=Decimal("990"),
    )


def test_position_sizing_approves_small_order() -> None:
    violations = PositionSizingRule().evaluate(_order(), _portfolio(), RiskLimitsConfig())
    assert violations == []


def test_position_sizing_rejects_oversized_order() -> None:
    violations = PositionSizingRule().evaluate(_order("2"), _portfolio(), RiskLimitsConfig())
    types = {item.violation_type for item in violations}
    assert RiskViolationType.ORDER_NOTIONAL_EXCEEDED in types


def test_position_sizing_rejects_position_limit() -> None:
    config = RiskLimitsConfig(max_order_notional_pct=Decimal("0.30"))
    violations = PositionSizingRule().evaluate(_order("2.6"), _portfolio(), config)
    types = {item.violation_type for item in violations}
    assert RiskViolationType.POSITION_SIZE_EXCEEDED in types
