from __future__ import annotations

import json
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    rng = random.Random(3)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    prices: dict[str, list[list[str]]] = {}
    for symbol, vol in (("BTCUSDT", 0.03), ("ETHUSDT", 0.04)):
        price = 100.0
        rows = []
        for day in range(400):
            price *= 1 + rng.gauss(0, vol)
            rows.append([(start + timedelta(days=day)).isoformat(), f"{price:.4f}"])
        prices[symbol] = rows
    prices_path = tmp_path / "prices.json"
    prices_path.write_text(json.dumps(prices), encoding="utf-8")
    positions = tmp_path / "positions.json"
    positions.write_text(
        json.dumps({"equity": "10000", "notionals": {"BTCUSDT": "3000", "ETHUSDT": "1000"}}),
        encoding="utf-8",
    )
    return prices_path, positions


def test_cli_portfolio_var_and_check(tmp_path: Path) -> None:
    prices, positions = _write_inputs(tmp_path)
    cli = [sys.executable, "-m", "risk_management_engine"]
    var = subprocess.run(
        [
            *cli,
            "portfolio-var",
            "--prices",
            str(prices),
            "--positions",
            str(positions),
            "--backtest-window",
            "250",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(var.stdout)
    assert report["observations"] == 399
    assert report["historical"]["cvar"] >= report["historical"]["var"] > 0
    assert {b["method"] for b in report["backtests"]} == {"historical", "parametric"}

    order = tmp_path / "order.json"
    order.write_text(
        json.dumps({"symbol": "BTCUSDT", "side": "buy", "quantity": "100", "price": "100"}),
        encoding="utf-8",
    )
    check = subprocess.run(
        [
            *cli,
            "check-portfolio",
            "--order",
            str(order),
            "--prices",
            str(prices),
            "--positions",
            str(positions),
            "--max-asset-exposure-pct",
            "0.35",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    verdict = json.loads(check.stdout)
    assert verdict["verdict"] == "rejected"
    assert "asset_exposure_exceeded" in {v["violation_type"] for v in verdict["violations"]}
