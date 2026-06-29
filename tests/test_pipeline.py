from __future__ import annotations

from pathlib import Path

from risk_management_engine.models import RiskLimitsConfig
from risk_management_engine.pipeline import run_risk_check_pipeline


def test_pipeline_runs_sample_files() -> None:
    root = Path(__file__).resolve().parents[1]
    results = run_risk_check_pipeline(
        orders_path=str(root / "samples" / "proposed_orders.jsonl"),
        portfolio_path=str(root / "samples" / "portfolio.json"),
        symbol="BTCUSDT",
        config=RiskLimitsConfig(),
    )
    assert len(results) == 3
    assert results[0]["verdict"] == "approved"
    assert results[1]["verdict"] == "rejected"
    assert results[2]["verdict"] == "rejected"
