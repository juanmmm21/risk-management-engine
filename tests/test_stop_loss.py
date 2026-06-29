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
from risk_management_engine.rules.stop_loss import StopLossRule


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


def test_stop_loss_requires_price_on_entry() -> None:
    order = ProposedOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        reference_price=Decimal("1000"),
        submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    violations = StopLossRule().evaluate(order, _portfolio(), RiskLimitsConfig())
    assert len(violations) == 1
    assert violations[0].violation_type is RiskViolationType.MISSING_STOP_LOSS


def test_stop_loss_rejects_stop_too_close() -> None:
    order = ProposedOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        reference_price=Decimal("1000"),
        submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        stop_loss_price=Decimal("999.9"),
    )
    violations = StopLossRule().evaluate(order, _portfolio(), RiskLimitsConfig())
    assert violations[0].violation_type is RiskViolationType.INVALID_STOP_LOSS
