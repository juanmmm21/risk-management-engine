"""Portfolio-level risk: VaR / CVaR, correlations and cross-asset exposure limits.

Losses are reported as **positive fractions of equity** (0.031 = 3.1 %). Statistics use ``float``;
exposures and money stay ``Decimal``.

* Historical VaR/CVaR: the empirical (1 - c) quantile of portfolio returns, taken at the lower
  order statistic (conservative), and the mean of the returns at or below it (expected shortfall).
* Parametric VaR/CVaR: normal returns with the portfolio mean and ``sqrt(wᵀ Σ w)``.
* Horizons longer than one period scale with ``sqrt(h)`` (parametric) and use overlapping h-period
  returns (historical).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from statistics import NormalDist

from risk_management_engine.models import OrderSide

_NORMAL = NormalDist()


class PortfolioViolationType(StrEnum):
    GROSS_EXPOSURE_EXCEEDED = "gross_exposure_exceeded"
    NET_EXPOSURE_EXCEEDED = "net_exposure_exceeded"
    ASSET_EXPOSURE_EXCEEDED = "asset_exposure_exceeded"
    CORRELATED_EXPOSURE_EXCEEDED = "correlated_exposure_exceeded"
    VAR_LIMIT_EXCEEDED = "var_limit_exceeded"
    CVAR_LIMIT_EXCEEDED = "cvar_limit_exceeded"
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass(frozen=True, slots=True)
class VarEstimate:
    method: str
    confidence: float
    horizon_periods: int
    var: float
    cvar: float


def historical_var_cvar(returns: Sequence[float], confidence: float) -> tuple[float, float]:
    _check_confidence(confidence)
    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    ordered = sorted(returns)
    index = max(0, math.floor((1.0 - confidence) * len(ordered)) - 1)
    threshold = ordered[index]
    tail = ordered[: index + 1]
    return max(0.0, -threshold), max(0.0, -math.fsum(tail) / len(tail))


def parametric_var_cvar(mean: float, std: float, confidence: float) -> tuple[float, float]:
    _check_confidence(confidence)
    if std < 0:
        raise ValueError("std must be non-negative")
    z = _NORMAL.inv_cdf(1.0 - confidence)
    var = -(mean + std * z)
    cvar = -(mean - std * _NORMAL.pdf(z) / (1.0 - confidence))
    return max(0.0, var), max(0.0, cvar)


def _check_confidence(confidence: float) -> None:
    if not 0.5 < confidence < 1.0:
        raise ValueError("confidence must be in (0.5, 1)")


def mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def covariance(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n != len(ys) or n < 2:
        raise ValueError("series must have the same length >= 2")
    mx, my = mean(xs), mean(ys)
    return math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (n - 1)


def correlation_matrix(returns: Mapping[str, Sequence[float]]) -> dict[str, dict[str, float]]:
    names = sorted(returns)
    std = {name: math.sqrt(covariance(returns[name], returns[name])) for name in names}
    matrix: dict[str, dict[str, float]] = {}
    for a in names:
        matrix[a] = {}
        for b in names:
            if a == b:
                matrix[a][b] = 1.0
            elif std[a] == 0.0 or std[b] == 0.0:
                matrix[a][b] = 0.0
            else:
                matrix[a][b] = covariance(returns[a], returns[b]) / (std[a] * std[b])
    return matrix


def align_returns(
    prices: Mapping[str, Sequence[tuple[datetime, Decimal]]], horizon: int = 1
) -> dict[str, list[float]]:
    """Simple ``horizon``-period returns on the timestamps every asset has (inner join)."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if not prices:
        return {}
    common = set.intersection(*(set(t for t, _ in series) for series in prices.values()))
    stamps = sorted(common)
    result: dict[str, list[float]] = {}
    for name, series in prices.items():
        by_time = dict(series)
        closes = [float(by_time[t]) for t in stamps]
        result[name] = [closes[i] / closes[i - horizon] - 1.0 for i in range(horizon, len(closes))]
    return result


@dataclass(frozen=True, slots=True)
class Exposure:
    """Signed notional per asset (quote currency) and the account equity."""

    notionals: Mapping[str, Decimal]
    equity: Decimal

    def weights(self) -> dict[str, float]:
        if self.equity <= 0:
            raise ValueError("equity must be positive")
        return {name: float(value / self.equity) for name, value in self.notionals.items()}

    @property
    def gross(self) -> Decimal:
        return sum((abs(v) for v in self.notionals.values()), Decimal("0"))

    @property
    def net(self) -> Decimal:
        return sum(self.notionals.values(), Decimal("0"))


def portfolio_var(
    exposure: Exposure,
    returns: Mapping[str, Sequence[float]],
    *,
    confidence: float = 0.99,
    horizon_periods: int = 1,
) -> tuple[VarEstimate, VarEstimate]:
    """(historical, parametric) VaR/CVaR of the exposure, as fractions of equity."""
    weights = {name: w for name, w in exposure.weights().items() if w != 0.0}
    missing = [name for name in weights if name not in returns]
    if missing:
        raise ValueError(f"no return history for {', '.join(sorted(missing))}")
    if not weights:
        zero = VarEstimate("historical", confidence, horizon_periods, 0.0, 0.0)
        return zero, VarEstimate("parametric", confidence, horizon_periods, 0.0, 0.0)
    length = min(len(returns[name]) for name in weights)
    series = [
        math.fsum(weights[name] * returns[name][i] for name in weights) for i in range(length)
    ]
    if horizon_periods > 1:
        series = [
            math.prod(1.0 + r for r in series[i : i + horizon_periods]) - 1.0
            for i in range(len(series) - horizon_periods + 1)
        ]
    h_var, h_cvar = historical_var_cvar(series, confidence)

    names = sorted(weights)
    one_period = {name: list(returns[name][:length]) for name in names}
    variance = math.fsum(
        weights[a] * weights[b] * covariance(one_period[a], one_period[b])
        for a in names
        for b in names
    )
    mu = math.fsum(weights[name] * mean(one_period[name]) for name in names)
    p_var, p_cvar = parametric_var_cvar(
        mu * horizon_periods, math.sqrt(max(variance, 0.0) * horizon_periods), confidence
    )
    return (
        VarEstimate("historical", confidence, horizon_periods, h_var, h_cvar),
        VarEstimate("parametric", confidence, horizon_periods, p_var, p_cvar),
    )


def correlated_groups(
    correlations: Mapping[str, Mapping[str, float]], threshold: float
) -> list[set[str]]:
    """Connected components of the graph where an edge means correlation >= threshold."""
    remaining = set(correlations)
    groups: list[set[str]] = []
    while remaining:
        seed = remaining.pop()
        group = {seed}
        frontier = [seed]
        while frontier:
            current = frontier.pop()
            for other in list(remaining):
                if correlations[current].get(other, 0.0) >= threshold:
                    remaining.discard(other)
                    group.add(other)
                    frontier.append(other)
        groups.append(group)
    return groups


@dataclass(frozen=True, slots=True)
class PortfolioRiskLimits:
    max_gross_exposure_pct: Decimal = Decimal("1.0")
    max_net_exposure_pct: Decimal = Decimal("1.0")
    max_asset_exposure_pct: Decimal = Decimal("0.5")
    max_correlated_exposure_pct: Decimal = Decimal("0.75")
    correlation_threshold: float = 0.7
    max_var_pct: float = 0.05
    max_cvar_pct: float = 0.07
    confidence: float = 0.99
    horizon_periods: int = 1
    min_history: int = 60


@dataclass(frozen=True, slots=True)
class PortfolioViolation:
    violation_type: PortfolioViolationType
    message: str


@dataclass(frozen=True, slots=True)
class PortfolioRiskReport:
    approved: bool
    risk_reducing: bool
    violations: tuple[PortfolioViolation, ...]
    before: dict[str, float]
    after: dict[str, float]
    correlations: dict[str, dict[str, float]] = field(default_factory=dict)


def _metrics(
    exposure: Exposure,
    returns: Mapping[str, Sequence[float]],
    limits: PortfolioRiskLimits,
    groups: list[set[str]],
) -> dict[str, float]:
    historical, parametric = portfolio_var(
        exposure, returns, confidence=limits.confidence, horizon_periods=limits.horizon_periods
    )
    equity = exposure.equity
    per_asset = {name: abs(value) / equity for name, value in exposure.notionals.items()}
    grouped = [
        sum((abs(exposure.notionals.get(name, Decimal("0"))) for name in group), Decimal("0"))
        / equity
        for group in groups
    ]
    return {
        "gross_exposure_pct": float(exposure.gross / equity),
        "net_exposure_pct": float(exposure.net / equity),
        "max_asset_exposure_pct": float(max(per_asset.values(), default=Decimal("0"))),
        "max_correlated_exposure_pct": float(max(grouped, default=Decimal("0"))),
        "historical_var": historical.var,
        "historical_cvar": historical.cvar,
        "parametric_var": parametric.var,
        "parametric_cvar": parametric.cvar,
        "var": max(historical.var, parametric.var),
        "cvar": max(historical.cvar, parametric.cvar),
    }


def check_portfolio_order(
    *,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    price: Decimal,
    exposure: Exposure,
    returns: Mapping[str, Sequence[float]],
    limits: PortfolioRiskLimits,
) -> PortfolioRiskReport:
    """Evaluate the portfolio as it would be after the order (pro forma).

    An order that lowers gross exposure and VaR is always allowed, so the gate can never block
    the way out of a breach.
    """
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be positive")
    short_history = [
        name
        for name in {*exposure.notionals, symbol}
        if len(returns.get(name, ())) < limits.min_history
    ]
    signed = price * quantity * (1 if side is OrderSide.BUY else -1)
    after_notionals = dict(exposure.notionals)
    after_notionals[symbol] = after_notionals.get(symbol, Decimal("0")) + signed
    after = Exposure(after_notionals, exposure.equity)
    if short_history:
        violation = PortfolioViolation(
            PortfolioViolationType.INSUFFICIENT_HISTORY,
            f"fewer than {limits.min_history} returns for {', '.join(sorted(short_history))}",
        )
        return PortfolioRiskReport(False, False, (violation,), {}, {})

    names = sorted(after_notionals)
    window = {name: list(returns[name]) for name in names}
    correlations = correlation_matrix(window) if len(names) > 1 else {names[0]: {names[0]: 1.0}}
    groups = correlated_groups(correlations, limits.correlation_threshold)
    before_metrics = _metrics(exposure, window, limits, groups)
    after_metrics = _metrics(after, window, limits, groups)
    reducing = (
        after.gross <= exposure.gross and after_metrics["var"] <= before_metrics["var"] + 1e-12
    )

    checks = (
        (
            PortfolioViolationType.GROSS_EXPOSURE_EXCEEDED,
            "gross_exposure_pct",
            float(limits.max_gross_exposure_pct),
        ),
        (
            PortfolioViolationType.NET_EXPOSURE_EXCEEDED,
            "net_exposure_pct",
            float(limits.max_net_exposure_pct),
        ),
        (
            PortfolioViolationType.ASSET_EXPOSURE_EXCEEDED,
            "max_asset_exposure_pct",
            float(limits.max_asset_exposure_pct),
        ),
        (
            PortfolioViolationType.CORRELATED_EXPOSURE_EXCEEDED,
            "max_correlated_exposure_pct",
            float(limits.max_correlated_exposure_pct),
        ),
        (PortfolioViolationType.VAR_LIMIT_EXCEEDED, "var", limits.max_var_pct),
        (PortfolioViolationType.CVAR_LIMIT_EXCEEDED, "cvar", limits.max_cvar_pct),
    )
    violations: list[PortfolioViolation] = []
    if not reducing:
        for kind, key, limit in checks:
            value = abs(after_metrics[key])
            if value > limit:
                violations.append(
                    PortfolioViolation(kind, f"{key} would be {value:.4f} > limit {limit:.4f}")
                )
    return PortfolioRiskReport(
        approved=not violations,
        risk_reducing=reducing,
        violations=tuple(violations),
        before=before_metrics,
        after=after_metrics,
        correlations=correlations,
    )


@dataclass(frozen=True, slots=True)
class VarBacktest:
    method: str
    confidence: float
    window: int
    observations: int
    exceedances: int
    expected_exceedances: float
    exceedance_rate: float
    kupiec_lr: float
    kupiec_p_value: float


def backtest_var(
    returns: Sequence[float], *, window: int, confidence: float, method: str
) -> VarBacktest:
    """Rolling one-step-ahead VaR; Kupiec's proportion-of-failures test on the exceedances."""
    if method not in {"historical", "parametric"}:
        raise ValueError("method must be historical or parametric")
    if window < 30 or len(returns) <= window:
        raise ValueError("need a window >= 30 and more returns than the window")
    exceed = 0
    n = len(returns) - window
    for i in range(window, len(returns)):
        past = returns[i - window : i]
        if method == "historical":
            var, _ = historical_var_cvar(past, confidence)
        else:
            mu = mean(past)
            var, _ = parametric_var_cvar(mu, math.sqrt(covariance(past, past)), confidence)
        if -returns[i] > var:
            exceed += 1
    p = 1.0 - confidence
    rate = exceed / n
    lr = _kupiec_lr(exceed, n, p)
    return VarBacktest(
        method=method,
        confidence=confidence,
        window=window,
        observations=n,
        exceedances=exceed,
        expected_exceedances=p * n,
        exceedance_rate=rate,
        kupiec_lr=lr,
        kupiec_p_value=math.erfc(math.sqrt(lr / 2.0)),
    )


def _kupiec_lr(failures: int, n: int, p: float) -> float:
    def log_likelihood(prob: float) -> float:
        total = 0.0
        if failures:
            total += failures * math.log(prob)
        if n - failures:
            total += (n - failures) * math.log(1.0 - prob)
        return total

    observed = failures / n
    if observed in (0.0, 1.0):
        return -2.0 * (log_likelihood(p) - 0.0)
    return -2.0 * (log_likelihood(p) - log_likelihood(observed))
