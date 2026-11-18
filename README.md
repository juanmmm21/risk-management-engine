# risk-management-engine

Pre-trade safety shield that **intercepts orders** before sending them to the market and verifies strict mathematical rules: position size, mandatory stop-loss, and maximum daily loss (*max drawdown*). Ninth module of the [quant-core-infra](https://github.com/juanmmm21/quant-core-infra) ecosystem.

Repository: [github.com/juanmmm21/risk-management-engine](https://github.com/juanmmm21/risk-management-engine)

---

## What it is and what problem it solves

A trading bot can generate signals that are technically valid but **dangerous** in terms of capital: orders that are too large, entries without a stop-loss, or trades during a critical daily drawdown.

This module acts as a **deterministic filter** between strategy logic and `order-routing-gateway`. No order reaches the exchange without passing through the risk engine.

---

## Role in quant-core-infra

```text
alpha-signal-generator ──► event-driven-backtester ──► ProposedOrder
                                                              │
                                                              ▼
                                                   risk-management-engine
                                                              │
                                         approved ────────────┼──────── rejected
                                                              ▼
                                                   order-routing-gateway
                                                              │
                                                   trade-audit-logger
```

It sits **before** routing and **after** order generation.

---

## Purpose

Demonstrates:

- Pre-trade rule engine extensible via `RiskRule`
- Position sizing validation with `Decimal`
- Mandatory stop-loss on new entries
- Blocking on maximum daily drawdown
- JSONL pipelines for proposed orders and portfolio snapshots

---

## Implemented rules

### Position sizing (`position_sizing`)

| Check | Rejection condition |
|-------|---------------------|
| Notional per order | `quantity × price > equity × max_order_notional_pct` |
| Position notional | `(pos + qty) × price > equity × max_position_notional_pct` |
| Available capital | `notional > cash` on buys |

### Stop-loss (`stop_loss`)

| Check | Rejection condition |
|-------|---------------------|
| Mandatory stop | New long entry without `stop_loss_price` |
| Valid stop | `stop_loss >= reference_price` on longs |
| Minimum distance | `(price - stop) / price < min_stop_loss_distance_pct` |

### Drawdown (`drawdown`)

```
drawdown_pct = (peak_equity_today - equity) / peak_equity_today
```

If `drawdown_pct >= max_daily_drawdown_pct` → blocks **new buys**. Sells (risk reduction) are still allowed.

---

## Portfolio risk (v0.2.0)

Per-order rules cannot see that a BTC long and an ETH long are mostly the same bet. The
`portfolio_risk` module looks at the whole book:

| Measure | Method |
|---------|--------|
| **Historical VaR / CVaR** | empirical (1 − c) quantile of portfolio returns (lower order statistic, conservative) and the mean of the tail at or below it |
| **Parametric VaR / CVaR** | normal with the portfolio mean and `sqrt(wᵀ Σ w)`; CVaR = −(μ − σ φ(z) / (1 − c)) |
| **Correlations** | Pearson matrix on aligned returns; assets with ρ ≥ threshold form a **correlated group** |
| **VaR backtest** | rolling one-step-ahead VaR, exceedance count and Kupiec proportion-of-failures test |

Pre-trade limits are checked on the **pro-forma** portfolio (after the order): gross and net
exposure, exposure per asset, exposure per correlated group, VaR and CVaR, plus a minimum return
history. An order that lowers both gross exposure and VaR is always approved, so the gate never
blocks the way out of a breach.

```bash
risk-management-engine portfolio-var --prices prices.json --positions positions.json \
  --confidence 0.99 --backtest-window 250
risk-management-engine check-portfolio --order order.json --prices prices.json \
  --positions positions.json --max-correlated-exposure-pct 0.75 --max-var-pct 0.05
```

`prices.json`: `{"BTCUSDT": [["2026-01-01T00:00:00Z", "93000.1"], ...]}`;
`positions.json`: `{"equity": "10000", "notionals": {"BTCUSDT": "4000", "ETHUSDT": "-1000"}}`.

### Measured on real data (2026-11-17)

Binance daily closes from `data-api.binance.vision`, 2024-11-17 → 2026-11-16 (729 daily returns),
portfolio 40 % BTC, 20 % ETH, 10 % SOL, 10 % BNB of 10,000 USDT, 4-vCPU Linux x86_64:

| 1-day, 99 % | Historical | Parametric |
|-------------|-----------|------------|
| VaR | 5.88 % (588 USDT) | 4.93 % (493 USDT) |
| CVaR | 7.72 % | 5.65 % |
| Backtest (479 days, window 250) | 4 exceedances vs 4.79 expected, Kupiec p = 0.71 | 6 vs 4.79, p = 0.59 |

Pairwise correlations were 0.70–0.84 (BTC–ETH 0.84), so with a 0.7 threshold all four assets
form one correlated group. Past VaR is a statistic of the past, not a bound on future losses.

---

## How it works

1. **Portfolio snapshot:** cash, equity, open position, daily PnL, and the day's peak.
2. **Proposed order:** quantity, reference price, and optional stop-loss.
3. **Evaluation:** each rule returns a `RiskViolation` or an empty list.
4. **Verdict:** `approved` with no violations; `rejected` with at least one.

---

## Architecture

```text
ProposedOrder + PortfolioSnapshot
              │
              ▼
    RiskManagementEngine
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
Drawdown  Position   StopLoss
 Rule      Sizing      Rule
              │
              ▼
       RiskCheckResult
```

### Components

| Module | Responsibility |
|--------|----------------|
| `rules/position_sizing.py` | Notional and capital limits |
| `rules/stop_loss.py` | Stop validation on entries |
| `rules/drawdown.py` | Daily drawdown blocking |
| `engine.py` | Rule orchestration |
| `ingest.py` | JSON/JSONL parsing |
| `pipeline.py` | End-to-end run |

---

## Configuration: `RiskLimitsConfig`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_position_notional_pct` | `0.25` | Max 25% of equity in position |
| `max_order_notional_pct` | `0.10` | Max 10% of equity per order |
| `max_daily_drawdown_pct` | `0.05` | Max daily drawdown 5% |
| `require_stop_loss_on_entry` | `true` | Mandatory stop on long entries |
| `min_stop_loss_distance_pct` | `0.005` | Minimum stop distance (0.5%) |

---

## Requirements

- Python **3.11+**

---

## Installation

```bash
cd risk-management-engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## CLI usage

```bash
risk-management-engine check \
  --orders samples/proposed_orders.jsonl \
  --portfolio samples/portfolio.json \
  --symbol BTCUSDT \
  --max-order-notional-pct 0.10 \
  --output risk_results.json
```

### Expected output (excerpt)

```json
{
  "client_order_id": "ord-no-stop",
  "verdict": "rejected",
  "violations": [
    {
      "rule_id": "stop_loss",
      "violation_type": "missing_stop_loss",
      "message": "stop_loss_price is required for new long entries"
    }
  ]
}
```

---

## Input formats

### Proposed order (JSONL)

```json
{
  "client_order_id": "ord-1",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": "0.01",
  "reference_price": "1000",
  "stop_loss_price": "990",
  "submitted_at": "2024-01-01T12:00:00.000Z"
}
```

### Portfolio snapshot (JSON)

```json
{
  "symbol": "BTCUSDT",
  "cash": "9500",
  "equity": "10000",
  "position_quantity": "0",
  "average_entry_price": "0",
  "daily_realized_pnl": "0",
  "peak_equity_today": "10000",
  "snapshot_time": "2024-01-01T12:00:00.000Z"
}
```

---

## Programmatic usage

```python
from datetime import UTC, datetime
from decimal import Decimal

from risk_management_engine import (
    PortfolioSnapshot,
    ProposedOrder,
    RiskLimitsConfig,
    RiskManagementEngine,
    run_risk_check_pipeline,
)

results = run_risk_check_pipeline(
    orders_path="orders.jsonl",
    portfolio_path="portfolio.json",
    symbol="BTCUSDT",
    config=RiskLimitsConfig(max_daily_drawdown_pct=Decimal("0.03")),
)

engine = RiskManagementEngine(RiskLimitsConfig())
check = engine.check_order(order, portfolio)
```

---

## Development

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Troubleshooting

| Symptom | Likely cause | Solution |
|---------|----------------|----------|
| All orders rejected for drawdown | `equity` far below `peak_equity_today` | Update the snapshot or adjust `max_daily_drawdown_pct` |
| `flat position must have zero average_entry_price` | Zero position with a non-zero average price | Set `average_entry_price: "0"` when `position_quantity` is 0 |
| `order symbol must match portfolio` | Mismatched symbols | Align `--symbol` and the `symbol` fields in both files |

---

## Roadmap

- [ ] Multi-symbol exposure and correlation rules
- [ ] Trailing stop and take-profit as additional validations
- [ ] Inline integration with `order-routing-gateway` as middleware
- [ ] Persisting violations in `trade-audit-logger`

---

## License

MIT
