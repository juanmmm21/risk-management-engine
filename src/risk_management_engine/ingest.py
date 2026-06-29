from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from risk_management_engine.models import (
    PortfolioSnapshot,
    ProposedOrder,
    decimal_from_value,
    parse_order_side,
    utc_from_iso8601,
)


def load_orders(path: str | Path, default_symbol: str) -> list[ProposedOrder]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"orders file not found: {file_path}")

    orders: list[ProposedOrder] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid json on line {line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            orders.append(parse_proposed_order(payload, default_symbol))

    if not orders:
        raise ValueError("orders file is empty")
    return orders


def load_portfolio_snapshot(path: str | Path, default_symbol: str) -> PortfolioSnapshot:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"portfolio file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError("portfolio file must contain valid json") from exc

    if not isinstance(payload, dict):
        raise ValueError("portfolio file must contain a JSON object")
    return parse_portfolio_snapshot(payload, default_symbol)


def parse_proposed_order(payload: dict[str, Any], default_symbol: str) -> ProposedOrder:
    order_id = payload.get("client_order_id") or payload.get("order_id")
    if not order_id:
        raise ValueError("missing client_order_id or order_id")

    required = ("side", "quantity", "reference_price", "submitted_at")
    for field in required:
        if field not in payload:
            raise ValueError(f"missing required field: {field}")

    symbol = str(payload.get("symbol", default_symbol))
    stop_loss_raw = payload.get("stop_loss_price")

    return ProposedOrder(
        client_order_id=str(order_id),
        symbol=symbol,
        side=parse_order_side(str(payload["side"])),
        quantity=decimal_from_value(payload["quantity"], "quantity"),
        reference_price=decimal_from_value(payload["reference_price"], "reference_price"),
        submitted_at=utc_from_iso8601(str(payload["submitted_at"])),
        stop_loss_price=(
            decimal_from_value(stop_loss_raw, "stop_loss_price")
            if stop_loss_raw is not None
            else None
        ),
        signal_id=str(payload.get("signal_id", "")),
    )


def parse_portfolio_snapshot(payload: dict[str, Any], default_symbol: str) -> PortfolioSnapshot:
    required = (
        "cash",
        "equity",
        "position_quantity",
        "average_entry_price",
        "daily_realized_pnl",
        "peak_equity_today",
        "snapshot_time",
    )
    for field in required:
        if field not in payload:
            raise ValueError(f"missing required field: {field}")

    symbol = str(payload.get("symbol", default_symbol))
    return PortfolioSnapshot(
        symbol=symbol,
        cash=decimal_from_value(payload["cash"], "cash"),
        equity=decimal_from_value(payload["equity"], "equity"),
        position_quantity=decimal_from_value(
            payload["position_quantity"],
            "position_quantity",
        ),
        average_entry_price=decimal_from_value(
            payload["average_entry_price"],
            "average_entry_price",
        ),
        daily_realized_pnl=decimal_from_value(payload["daily_realized_pnl"], "daily_realized_pnl"),
        peak_equity_today=decimal_from_value(payload["peak_equity_today"], "peak_equity_today"),
        snapshot_time=utc_from_iso8601(str(payload["snapshot_time"])),
    )
