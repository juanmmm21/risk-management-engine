from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from risk_management_engine.engine import RiskManagementEngine
from risk_management_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskVerdict,
)


def test_engine_approves_valid_order() -> None:
    engine = RiskManagementEngine(RiskLimitsConfig())
    portfolio = PortfolioSnapshot(
        symbol="BTCUSDT",
        cash=Decimal("9500"),
        equity=Decimal("10000"),
        position_quantity=Decimal("0"),
        average_entry_price=Decimal("0"),
        daily_realized_pnl=Decimal("0"),
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
    result = engine.check_order(order, portfolio)
    assert result.verdict is RiskVerdict.APPROVED
