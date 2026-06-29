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
from risk_management_engine.rules.drawdown import DrawdownRule


def test_drawdown_blocks_new_buys_when_limit_reached() -> None:
    portfolio = PortfolioSnapshot(
        symbol="BTCUSDT",
        cash=Decimal("9000"),
        equity=Decimal("9400"),
        position_quantity=Decimal("0"),
        average_entry_price=Decimal("0"),
        daily_realized_pnl=Decimal("-600"),
        peak_equity_today=Decimal("10000"),
        snapshot_time=datetime(2024, 1, 1, tzinfo=UTC),
    )
    order = ProposedOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        reference_price=Decimal("1000"),
        submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        stop_loss_price=Decimal("990"),
    )
    violations = DrawdownRule().evaluate(order, portfolio, RiskLimitsConfig())
    assert violations[0].violation_type is RiskViolationType.MAX_DRAWDOWN_EXCEEDED


def test_drawdown_allows_sells_during_drawdown() -> None:
    portfolio = PortfolioSnapshot(
        symbol="BTCUSDT",
        cash=Decimal("9000"),
        equity=Decimal("9400"),
        position_quantity=Decimal("0.05"),
        average_entry_price=Decimal("1000"),
        daily_realized_pnl=Decimal("-600"),
        peak_equity_today=Decimal("10000"),
        snapshot_time=datetime(2024, 1, 1, tzinfo=UTC),
    )
    order = ProposedOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        quantity=Decimal("0.01"),
        reference_price=Decimal("1000"),
        submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    violations = DrawdownRule().evaluate(order, portfolio, RiskLimitsConfig())
    assert violations == []
