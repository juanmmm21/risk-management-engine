from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal

from risk_management_engine.models import RiskLimitsConfig
from risk_management_engine.pipeline import run_risk_check_pipeline


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

    return parser


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

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
