from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from risk_management_engine.models import (
    OrderSide,
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
)


def test_proposed_order_requires_positive_reference_price() -> None:
    with pytest.raises(ValueError, match="reference_price must be positive"):
        ProposedOrder(
            client_order_id="ord-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            reference_price=Decimal("0"),
            submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        )


def test_portfolio_rejects_negative_position_quantity() -> None:
    with pytest.raises(ValueError, match="position_quantity must be non-negative"):
        PortfolioSnapshot(
            symbol="BTCUSDT",
            cash=Decimal("1000"),
            equity=Decimal("1000"),
            position_quantity=Decimal("-1"),
            average_entry_price=Decimal("0"),
            daily_realized_pnl=Decimal("0"),
            peak_equity_today=Decimal("1000"),
            snapshot_time=datetime(2024, 1, 1, tzinfo=UTC),
        )


def test_risk_limits_config_rejects_invalid_pct() -> None:
    with pytest.raises(ValueError, match="max_order_notional_pct"):
        RiskLimitsConfig(max_order_notional_pct=Decimal("1.5"))
