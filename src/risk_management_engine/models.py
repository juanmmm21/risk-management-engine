from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class RiskVerdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskViolationType(StrEnum):
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    ORDER_NOTIONAL_EXCEEDED = "order_notional_exceeded"
    MISSING_STOP_LOSS = "missing_stop_loss"
    INVALID_STOP_LOSS = "invalid_stop_loss"
    MAX_DRAWDOWN_EXCEEDED = "max_drawdown_exceeded"
    INSUFFICIENT_CAPITAL = "insufficient_capital"
    RULE_EVALUATION_ERROR = "rule_evaluation_error"


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    reference_price: Decimal
    submitted_at: datetime
    stop_loss_price: Decimal | None = None
    signal_id: str = ""

    def __post_init__(self) -> None:
        if not self.client_order_id:
            raise ValueError("client_order_id must not be empty")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.quantity <= Decimal("0"):
            raise ValueError("quantity must be positive")
        if self.reference_price <= Decimal("0"):
            raise ValueError("reference_price must be positive")
        if self.submitted_at.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        if self.stop_loss_price is not None and self.stop_loss_price <= Decimal("0"):
            raise ValueError("stop_loss_price must be positive")

    @property
    def notional(self) -> Decimal:
        return self.reference_price * self.quantity

    def increases_exposure(self, position_quantity: Decimal) -> bool:
        if self.side is OrderSide.BUY:
            return True
        return position_quantity > Decimal("0") and self.quantity < position_quantity


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    symbol: str
    cash: Decimal
    equity: Decimal
    position_quantity: Decimal
    average_entry_price: Decimal
    daily_realized_pnl: Decimal
    peak_equity_today: Decimal
    snapshot_time: datetime

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.cash < Decimal("0"):
            raise ValueError("cash must be non-negative")
        if self.equity <= Decimal("0"):
            raise ValueError("equity must be positive")
        if self.position_quantity < Decimal("0"):
            raise ValueError("position_quantity must be non-negative")
        if self.average_entry_price < Decimal("0"):
            raise ValueError("average_entry_price must be non-negative")
        if self.peak_equity_today <= Decimal("0"):
            raise ValueError("peak_equity_today must be positive")
        if self.snapshot_time.tzinfo is None:
            raise ValueError("snapshot_time must be timezone-aware")
        if self.position_quantity == Decimal("0") and self.average_entry_price != Decimal("0"):
            raise ValueError("flat position must have zero average_entry_price")

    @property
    def position_notional(self) -> Decimal:
        return self.position_quantity * self.average_entry_price

    @property
    def daily_drawdown_pct(self) -> Decimal:
        if self.peak_equity_today <= Decimal("0"):
            return Decimal("0")
        drawdown = (self.peak_equity_today - self.equity) / self.peak_equity_today
        return max(drawdown, Decimal("0"))


@dataclass(frozen=True, slots=True)
class RiskLimitsConfig:
    max_position_notional_pct: Decimal = Decimal("0.25")
    max_order_notional_pct: Decimal = Decimal("0.10")
    max_daily_drawdown_pct: Decimal = Decimal("0.05")
    require_stop_loss_on_entry: bool = True
    min_stop_loss_distance_pct: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_position_notional_pct", self.max_position_notional_pct),
            ("max_order_notional_pct", self.max_order_notional_pct),
            ("max_daily_drawdown_pct", self.max_daily_drawdown_pct),
            ("min_stop_loss_distance_pct", self.min_stop_loss_distance_pct),
        ):
            if value <= Decimal("0") or value > Decimal("1"):
                raise ValueError(f"{field_name} must be between 0 and 1 exclusive of 0")


@dataclass(frozen=True, slots=True)
class RiskViolation:
    rule_id: str
    violation_type: RiskViolationType
    message: str

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must not be empty")
        if not self.message:
            raise ValueError("message must not be empty")


@dataclass(frozen=True, slots=True)
class RiskCheckResult:
    client_order_id: str
    verdict: RiskVerdict
    violations: tuple[RiskViolation, ...]
    evaluated_at: datetime
    order_notional: Decimal
    equity: Decimal

    def __post_init__(self) -> None:
        if not self.client_order_id:
            raise ValueError("client_order_id must not be empty")
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.verdict is RiskVerdict.APPROVED and self.violations:
            raise ValueError("approved result cannot contain violations")
        if self.verdict is RiskVerdict.REJECTED and not self.violations:
            raise ValueError("rejected result must contain at least one violation")


def utc_from_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def decimal_from_value(value: object, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        return Decimal(str(value))
    raise ValueError(f"{field_name} must be numeric")


def parse_order_side(value: str) -> OrderSide:
    try:
        return OrderSide(value)
    except ValueError as exc:
        raise ValueError(f"unsupported order side: {value}") from exc
