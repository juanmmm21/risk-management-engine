from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal

from risk_management_engine.models import RiskLimitsConfig
from risk_management_engine.pipeline import run_risk_check_pipeline
from risk_management_engine.portfolio_pipeline import (
    check_order_report,
    load_exposure,
    load_prices,
    portfolio_var_report,
)
from risk_management_engine.portfolio_risk import PortfolioRiskLimits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Motor de gestión de riesgo pre-trade para validar órdenes.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check",
        help="Valida órdenes propuestas contra un snapshot de cartera.",
    )
    check.add_argument("--orders", required=True)
    check.add_argument("--portfolio", required=True)
    check.add_argument("--symbol", required=True)
    check.add_argument("--max-position-notional-pct", default="0.25")
    check.add_argument("--max-order-notional-pct", default="0.10")
    check.add_argument("--max-daily-drawdown-pct", default="0.05")
    check.add_argument("--min-stop-loss-distance-pct", default="0.005")
    check.add_argument("--require-stop-loss", action=argparse.BooleanOptionalAction, default=True)
    check.add_argument("--output", default=None)

    var = subparsers.add_parser("portfolio-var", help="VaR/CVaR histórico y paramétrico.")
    var.add_argument("--prices", required=True)
    var.add_argument("--positions", required=True)
    var.add_argument("--confidence", type=float, default=0.99)
    var.add_argument("--horizon", type=int, default=1)
    var.add_argument("--backtest-window", type=int, default=None)
    var.add_argument("--output", default=None)

    portfolio = subparsers.add_parser(
        "check-portfolio", help="Valida una orden contra los límites de cartera (pro forma)."
    )
    portfolio.add_argument("--order", required=True, help="Orden JSON.")
    portfolio.add_argument("--prices", required=True)
    portfolio.add_argument("--positions", required=True)
    portfolio.add_argument("--max-gross-exposure-pct", default="1.0")
    portfolio.add_argument("--max-net-exposure-pct", default="1.0")
    portfolio.add_argument("--max-asset-exposure-pct", default="0.5")
    portfolio.add_argument("--max-correlated-exposure-pct", default="0.75")
    portfolio.add_argument("--correlation-threshold", type=float, default=0.7)
    portfolio.add_argument("--max-var-pct", type=float, default=0.05)
    portfolio.add_argument("--max-cvar-pct", type=float, default=0.07)
    portfolio.add_argument("--confidence", type=float, default=0.99)
    portfolio.add_argument("--min-history", type=int, default=60)
    portfolio.add_argument("--output", default=None)

    return parser


def _emit(payload: object, output: str | None) -> None:
    rendered = json.dumps(payload, indent=2)
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        return
    print(rendered)


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.command == "check":
        config = RiskLimitsConfig(
            max_position_notional_pct=Decimal(args.max_position_notional_pct),
            max_order_notional_pct=Decimal(args.max_order_notional_pct),
            max_daily_drawdown_pct=Decimal(args.max_daily_drawdown_pct),
            require_stop_loss_on_entry=args.require_stop_loss,
            min_stop_loss_distance_pct=Decimal(args.min_stop_loss_distance_pct),
        )
        results = run_risk_check_pipeline(
            orders_path=args.orders,
            portfolio_path=args.portfolio,
            symbol=args.symbol,
            config=config,
        )
        rendered = json.dumps(results, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.write("\n")
            logging.getLogger(__name__).info(
                "wrote %s risk check results to %s",
                len(results),
                args.output,
            )
            return
        print(rendered)
        return

    if args.command == "portfolio-var":
        _emit(
            portfolio_var_report(
                load_prices(args.prices),
                load_exposure(args.positions),
                confidence=args.confidence,
                horizon=args.horizon,
                backtest_window=args.backtest_window,
            ),
            args.output,
        )
        return

    if args.command == "check-portfolio":
        limits = PortfolioRiskLimits(
            max_gross_exposure_pct=Decimal(args.max_gross_exposure_pct),
            max_net_exposure_pct=Decimal(args.max_net_exposure_pct),
            max_asset_exposure_pct=Decimal(args.max_asset_exposure_pct),
            max_correlated_exposure_pct=Decimal(args.max_correlated_exposure_pct),
            correlation_threshold=args.correlation_threshold,
            max_var_pct=args.max_var_pct,
            max_cvar_pct=args.max_cvar_pct,
            confidence=args.confidence,
            min_history=args.min_history,
        )
        with open(args.order, encoding="utf-8") as handle:
            order = json.load(handle)
        _emit(
            check_order_report(
                order, load_prices(args.prices), load_exposure(args.positions), limits
            ),
            args.output,
        )
        return

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
