"""JSON in / JSON out for portfolio risk (used by the CLI and by quant-terminal-web).

``prices.json``: ``{"BTCUSDT": [["2026-01-01T00:00:00Z", "93000.1"], ...], ...}`` (closes).
``positions.json``: ``{"equity": "10000", "notionals": {"BTCUSDT": "5000", "ETHUSDT": "-1000"}}``
(signed notionals in the quote currency).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from risk_management_engine.models import OrderSide, utc_from_iso8601
from risk_management_engine.portfolio_risk import (
    Exposure,
    PortfolioRiskLimits,
    align_returns,
    backtest_var,
    check_portfolio_order,
    correlation_matrix,
    portfolio_var,
)


def load_prices(path: str | Path) -> dict[str, list[tuple[datetime, Decimal]]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("prices file must map symbols to [[time, close], ...]")
    return {
        str(symbol): [(utc_from_iso8601(str(t)), Decimal(str(close))) for t, close in rows]
        for symbol, rows in raw.items()
    }


def load_exposure(path: str | Path) -> Exposure:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    notionals = {str(k): Decimal(str(v)) for k, v in raw.get("notionals", {}).items()}
    return Exposure(notionals=notionals, equity=Decimal(str(raw["equity"])))


def portfolio_var_report(
    prices: dict[str, list[tuple[datetime, Decimal]]],
    exposure: Exposure,
    *,
    confidence: float,
    horizon: int,
    backtest_window: int | None,
) -> dict[str, Any]:
    returns = align_returns(prices)
    historical, parametric = portfolio_var(
        exposure, returns, confidence=confidence, horizon_periods=horizon
    )
    report: dict[str, Any] = {
        "observations": min((len(v) for v in returns.values()), default=0),
        "confidence": confidence,
        "horizon_periods": horizon,
        "equity": str(exposure.equity),
        "gross_exposure_pct": float(exposure.gross / exposure.equity),
        "net_exposure_pct": float(exposure.net / exposure.equity),
        "historical": asdict(historical),
        "parametric": asdict(parametric),
        "var_quote": {
            "historical": float(exposure.equity) * historical.var,
            "parametric": float(exposure.equity) * parametric.var,
        },
        "correlations": correlation_matrix(returns) if len(returns) > 1 else {},
        "backtests": [],
    }
    if backtest_window:
        weights = exposure.weights()
        names = [name for name, weight in weights.items() if weight]
        length = min(len(returns[name]) for name in names)
        series = [sum(weights[n] * returns[n][i] for n in names) for i in range(length)]
        for method in ("historical", "parametric"):
            report["backtests"].append(
                asdict(backtest_var(series, window=backtest_window, confidence=confidence,
                                    method=method))
            )
    return report


def check_order_report(
    order: dict[str, Any],
    prices: dict[str, list[tuple[datetime, Decimal]]],
    exposure: Exposure,
    limits: PortfolioRiskLimits,
) -> dict[str, Any]:
    result = check_portfolio_order(
        symbol=str(order["symbol"]),
        side=OrderSide(str(order["side"])),
        quantity=Decimal(str(order["quantity"])),
        price=Decimal(str(order["price"])),
        exposure=exposure,
        returns=align_returns(prices),
        limits=limits,
    )
    return {
        "client_order_id": order.get("client_order_id"),
        "verdict": "approved" if result.approved else "rejected",
        "risk_reducing": result.risk_reducing,
        "violations": [
            {"violation_type": v.violation_type.value, "message": v.message}
            for v in result.violations
        ],
        "before": result.before,
        "after": result.after,
    }
