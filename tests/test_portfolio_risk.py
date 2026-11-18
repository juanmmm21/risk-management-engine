from __future__ import annotations

import math
import random
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from risk_management_engine.models import OrderSide
from risk_management_engine.portfolio_risk import (
    Exposure,
    PortfolioRiskLimits,
    PortfolioViolationType,
    backtest_var,
    check_portfolio_order,
    correlated_groups,
    correlation_matrix,
    historical_var_cvar,
    parametric_var_cvar,
    portfolio_var,
)


def test_parametric_matches_closed_form() -> None:
    var, cvar = parametric_var_cvar(0.0, 0.01, 0.99)
    assert var == pytest.approx(0.023263, abs=1e-6)
    assert cvar == pytest.approx(0.026652, abs=1e-6)


def test_historical_uses_the_lower_order_statistic_and_tail_mean() -> None:
    returns = [-0.10, -0.05, -0.02] + [0.01] * 97
    var, cvar = historical_var_cvar(returns, 0.98)  # 2 % of 100 -> 2nd worst
    assert var == pytest.approx(0.05)
    assert cvar == pytest.approx(0.075)


def _series(seed: int, n: int = 500, scale: float = 0.02) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0.0, scale) for _ in range(n)]


def test_diversification_lowers_parametric_var() -> None:
    a, b = _series(1), _series(2)
    equity = Decimal("10000")
    both = Exposure({"A": Decimal("5000"), "B": Decimal("5000")}, equity)
    same = Exposure({"A": Decimal("5000"), "A2": Decimal("5000")}, equity)
    _, uncorrelated = portfolio_var(both, {"A": a, "B": b})
    _, identical = portfolio_var(same, {"A": a, "A2": list(a)})
    assert uncorrelated.var < identical.var
    assert identical.var == pytest.approx(
        parametric_var_cvar(
            sum(a) / len(a),
            math.sqrt(sum((x - sum(a) / len(a)) ** 2 for x in a) / (len(a) - 1)),
            0.99,
        )[0],
        rel=1e-9,
    )


def test_short_positions_hedge_long_ones() -> None:
    a = _series(3)
    hedged = Exposure({"A": Decimal("5000"), "A2": Decimal("-5000")}, Decimal("10000"))
    historical, parametric = portfolio_var(hedged, {"A": a, "A2": list(a)})
    assert historical.var == pytest.approx(0.0, abs=1e-12)
    assert parametric.var == pytest.approx(0.0, abs=1e-12)


def test_correlations_and_groups() -> None:
    base = _series(4)
    noisy = [x + y for x, y in zip(base, _series(5, scale=0.002), strict=True)]
    returns = {"BTC": base, "ETH": noisy, "XAU": _series(6)}
    matrix = correlation_matrix(returns)
    assert matrix["BTC"]["ETH"] == pytest.approx(matrix["ETH"]["BTC"])
    assert matrix["BTC"]["ETH"] > 0.95
    assert abs(matrix["BTC"]["XAU"]) < 0.2
    groups = sorted(sorted(g) for g in correlated_groups(matrix, 0.7))
    assert groups == [["BTC", "ETH"], ["XAU"]]


def _history() -> dict[str, list[float]]:
    base = _series(7)
    return {
        "BTCUSDT": base,
        "ETHUSDT": [x * 1.2 + y for x, y in zip(base, _series(8, scale=0.004), strict=True)],
        "XAUT": _series(9, scale=0.008),
    }


LIMITS = PortfolioRiskLimits(
    max_gross_exposure_pct=Decimal("1.0"),
    max_net_exposure_pct=Decimal("1.0"),
    max_asset_exposure_pct=Decimal("0.6"),
    max_correlated_exposure_pct=Decimal("0.7"),
    max_var_pct=0.05,
    max_cvar_pct=0.06,
)


def test_correlated_exposure_limit_blocks_a_second_crypto_long() -> None:
    exposure = Exposure({"BTCUSDT": Decimal("5000")}, Decimal("10000"))
    report = check_portfolio_order(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        price=Decimal("3000"),
        exposure=exposure,
        returns=_history(),
        limits=LIMITS,
    )
    kinds = {v.violation_type for v in report.violations}
    assert not report.approved
    assert PortfolioViolationType.CORRELATED_EXPOSURE_EXCEEDED in kinds
    # the same notional in an uncorrelated asset passes the correlation limit
    report_xau = check_portfolio_order(
        symbol="XAUT",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        price=Decimal("3000"),
        exposure=exposure,
        returns=_history(),
        limits=LIMITS,
    )
    assert PortfolioViolationType.CORRELATED_EXPOSURE_EXCEEDED not in {
        v.violation_type for v in report_xau.violations
    }


def test_var_limit_and_risk_reducing_orders() -> None:
    tight = PortfolioRiskLimits(
        max_var_pct=0.01, max_cvar_pct=0.5, max_asset_exposure_pct=Decimal("1")
    )
    big = Exposure({"BTCUSDT": Decimal("9000")}, Decimal("10000"))
    adding = check_portfolio_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        price=Decimal("60000"),
        exposure=big,
        returns=_history(),
        limits=tight,
    )
    assert PortfolioViolationType.VAR_LIMIT_EXCEEDED in {
        v.violation_type for v in adding.violations
    }
    reducing = check_portfolio_order(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        quantity=Decimal("0.05"),
        price=Decimal("60000"),
        exposure=big,
        returns=_history(),
        limits=tight,
    )
    assert reducing.approved and reducing.risk_reducing
    assert reducing.after["var"] < reducing.before["var"]


def test_insufficient_history_rejects() -> None:
    report = check_portfolio_order(
        symbol="NEWUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        price=Decimal("10"),
        exposure=Exposure({}, Decimal("10000")),
        returns={"NEWUSDT": [0.01] * 10},
        limits=LIMITS,
    )
    assert report.violations[0].violation_type is PortfolioViolationType.INSUFFICIENT_HISTORY


def test_backtest_is_calibrated_on_normal_returns_and_flags_fat_tails() -> None:
    normal = _series(10, n=3000)
    result = backtest_var(normal, window=250, confidence=0.99, method="parametric")
    assert result.observations == 2750
    assert 0.004 < result.exceedance_rate < 0.02
    rng = random.Random(11)
    # Student-t with 3 dof: same scale, much fatter tails -> parametric VaR is breached too often
    fat = [rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 2) / 3) * 0.01 for _ in range(3000)]
    fat_result = backtest_var(fat, window=250, confidence=0.99, method="parametric")
    assert fat_result.exceedances > fat_result.expected_exceedances
    assert fat_result.kupiec_p_value < result.kupiec_p_value


@settings(max_examples=100, deadline=None)
@given(
    st.lists(st.floats(min_value=-0.2, max_value=0.2), min_size=20, max_size=200),
    st.floats(min_value=0.9, max_value=0.98),
)
def test_property_cvar_dominates_var_and_var_grows_with_confidence(
    returns: list[float], confidence: float
) -> None:
    var, cvar = historical_var_cvar(returns, confidence)
    var_hi, _ = historical_var_cvar(returns, 0.99)
    assert cvar >= var - 1e-12
    assert var_hi >= var - 1e-12
