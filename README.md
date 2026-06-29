# risk-management-engine

Escudo de seguridad pre-trade que **intercepta órdenes** antes de enviarlas al mercado y verifica reglas matemáticas estrictas: tamaño de posición, stop-loss obligatorio y pérdida máxima diaria (*max drawdown*). Noveno módulo del ecosistema [quant-core-infra](https://github.com/juanmmm21/quant-core-infra).

Repositorio: [github.com/juanmmm21/risk-management-engine](https://github.com/juanmmm21/risk-management-engine)

---

## Qué es y qué problema resuelve

Un bot de trading puede generar señales válidas técnicamente pero **peligrosas** en términos de capital: órdenes demasiado grandes, entradas sin stop-loss o operaciones durante un drawdown diario crítico.

Este módulo actúa como **filtro determinista** entre la lógica de estrategia y `order-routing-gateway`. Ninguna orden llega al exchange sin pasar por el motor de riesgo.

---

## Rol en quant-core-infra

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

Se sitúa **antes** del enrutamiento y **después** de la generación de órdenes.

---

## Objetivo

Demuestra:

- Motor de reglas pre-trade extensible mediante `RiskRule`
- Validación de position sizing con `Decimal`
- Stop-loss obligatorio en entradas nuevas
- Bloqueo por max drawdown diario
- Pipelines JSONL para órdenes propuestas y snapshot de cartera

---

## Reglas implementadas

### Position sizing (`position_sizing`)

| Check | Condición de rechazo |
|-------|---------------------|
| Notional por orden | `quantity × price > equity × max_order_notional_pct` |
| Notional de posición | `(pos + qty) × price > equity × max_position_notional_pct` |
| Capital disponible | `notional > cash` en compras |

### Stop-loss (`stop_loss`)

| Check | Condición de rechazo |
|-------|---------------------|
| Stop obligatorio | Entrada long nueva sin `stop_loss_price` |
| Stop válido | `stop_loss >= reference_price` en long |
| Distancia mínima | `(price - stop) / price < min_stop_loss_distance_pct` |

### Drawdown (`drawdown`)

```
drawdown_pct = (peak_equity_today - equity) / peak_equity_today
```

Si `drawdown_pct >= max_daily_drawdown_pct` → bloquea **nuevas compras**. Las ventas (reducción de riesgo) siguen permitidas.

---

## Cómo funciona

1. **Snapshot de cartera:** cash, equity, posición abierta, PnL diario y pico del día.
2. **Orden propuesta:** cantidad, precio de referencia y stop-loss opcional.
3. **Evaluación:** cada regla devuelve `RiskViolation` o lista vacía.
4. **Veredicto:** `approved` sin violaciones; `rejected` con al menos una.

---

## Arquitectura

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

### Componentes

| Módulo | Responsabilidad |
|--------|----------------|
| `rules/position_sizing.py` | Límites de notional y capital |
| `rules/stop_loss.py` | Validación de stop en entradas |
| `rules/drawdown.py` | Bloqueo por drawdown diario |
| `engine.py` | Orquestación de reglas |
| `ingest.py` | Parsing JSON/JSONL |
| `pipeline.py` | Run end-to-end |

---

## Configuración: `RiskLimitsConfig`

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `max_position_notional_pct` | `0.25` | Máximo 25% del equity en posición |
| `max_order_notional_pct` | `0.10` | Máximo 10% del equity por orden |
| `max_daily_drawdown_pct` | `0.05` | Drawdown diario máximo 5% |
| `require_stop_loss_on_entry` | `true` | Stop obligatorio en entradas long |
| `min_stop_loss_distance_pct` | `0.005` | Distancia mínima del stop (0.5%) |

---

## Requisitos

- Python **3.11+**

---

## Instalación

```bash
cd risk-management-engine
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Uso CLI

```bash
risk-management-engine check \
  --orders samples/proposed_orders.jsonl \
  --portfolio samples/portfolio.json \
  --symbol BTCUSDT \
  --max-order-notional-pct 0.10 \
  --output risk_results.json
```

### Salida esperada (extracto)

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

## Formatos de entrada

### Orden propuesta (JSONL)

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

### Snapshot de cartera (JSON)

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

## Uso programático

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

## Desarrollo

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| Todas las órdenes rechazadas por drawdown | `equity` muy por debajo de `peak_equity_today` | Actualiza el snapshot o ajusta `max_daily_drawdown_pct` |
| `flat position must have zero average_entry_price` | Posición cero con precio medio distinto de 0 | Pon `average_entry_price: "0"` cuando `position_quantity` es 0 |
| `order symbol must match portfolio` | Símbolos distintos | Alinea `--symbol` y campos `symbol` en ambos archivos |

---

## Roadmap

- [ ] Reglas de exposición multi-símbolo y correlación
- [ ] Trailing stop y take-profit como validaciones adicionales
- [ ] Integración en línea con `order-routing-gateway` como middleware
- [ ] Persistencia de violaciones en `trade-audit-logger`

---

## Licencia

MIT
