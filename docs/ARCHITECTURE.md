# Quantbot Architecture Overview

This document captures the major components of the trading stack as of this refactor. The
repository follows a typed, service-oriented layout rooted at the `quantbot/` package.

## Top-Level Layout

- `quantbot/config/` – Typed configuration models (`AppConfig`, `RuntimeConfig`, etc.) and the
  `get_config()` loader used everywhere. Configuration may be loaded from TOML files in
  `configs/` and augmented by environment variables (see `ENVIRONMENT`, `MODE`, `EXCHANGE`,
  `SYMBOL`, etc.).
- `quantbot/core/` – Shared event primitives (`MarketEvent`, `SignalEvent`, `OrderRequest`,
  `FillEvent`) that ensure parity between backtest, paper, and live execution.
- `quantbot/data/` – Market data primitives (`Bar`, `Trade`, `BookSnapshot`) and the
  `MarketNormalizer` that produces `MarketState` objects consumed by strategies and the
  execution stack.
- `quantbot/backtest/` – Event-driven backtest engine, dataset helpers, and performance
  analytics. The engine now writes structured replay logs (`events.jsonl`) per run.
- `quantbot/exchange/` – Exchange adapter protocol plus the Binance Futures and Hyperliquid
  implementations. Adapters share precision handling, rate limiting, and simulate fills via an
  in-memory state helper during offline development.
- `quantbot/risk/` – Central `RiskManager`, funding model, stop utilities, and compatibility
  shims (`LimitChecker`, `StopManager`). All order flow—backtest and paper/live—runs through the
  shared risk layer which enforces per-order and per-day limits plus a kill switch.
- `quantbot/live/` – Paper/live runner, heartbeat watchdog, and FastAPI status service.
- `quantbot/exec/` – Broker protocol, paper broker, router helpers, and position tracking.
- `quantbot/storage/` – SQLAlchemy-backed persistence helpers for metrics and historical data.
- `quantbot/logging_setup.py` – JSON logging configuration injecting environment/mode/exchange
  metadata into every log line.

## Entry Points

- **Backtest:** `python -m quantbot.backtest.engine --config configs/binance_backtest.toml` (also
  exposed via `make run-backtest`). Uses the new `BacktestEngine` which drives strategies through
  the shared event/risk/normalisation stack.
- **Paper trading:** `python -m quantbot.live.runner --mode paper --config configs/binance_paper.toml`.
  Reuses the same `MarketNormalizer`, `RiskManager`, and order routing helpers as the backtest.
- **FastAPI status service:** `quantbot/api/status.py` exposes `/health/live`, `/health/ready`, and
  `/metrics` endpoints and can be served with `uvicorn quantbot.api.status:app`.
- **Exchange adapters:** `quantbot.exchange.binance.BinanceFuturesAdapter` and
  `quantbot.exchange.hyperliquid.HyperliquidPerpAdapter` implement the shared `ExchangeAdapter`
  protocol with precision enforcement, rate-limiting, and retry scaffolding.

## Configuration & Environments

- All runtime state flows through `AppConfig`. Nested sections (`runtime`, `risk`, `data`, `api`,
  `fees`, `logging`, `storage`) provide strict validation, fail-fast defaults, and environment-
  variable overrides. `ENVIRONMENT` (`dev|staging|prod`) is mandatory.
- Sample TOML files live in `configs/` for common scenarios (Binance backtest, Binance paper,
  Hyperliquid backtest).
- Logging attaches `env`, `mode`, `exchange`, `symbols`, and `run_id` to every message.

## Event Model & Risk Flow

1. Market data is normalised into `MarketState` objects by `MarketNormalizer`.
2. The backtest/paper runners generate `MarketEvent` instances that feed strategies.
3. Strategies emit `SignalEvent` (target position) which the execution layer translates into
   `OrderRequest` objects.
4. Every order request is filtered by `RiskManager.validate_order`, enforcing leverage, notional,
   spread sanity, max-open-positions, long-only/short-only, and kill-switch checks.
5. Approved orders are executed (simulated in backtest/paper) and `RiskManager.on_fill` updates
   exposure, drawdown, and PnL tracking. Funding accruals and kill-switch triggers are recorded as
   replay events.

## Observability

- Structured JSON logging with consistent metadata plus optional per-log extras via `log_extra`.
- `quantbot/api/status` keeps aggregate metrics (PnL, positions, custom counters) and exposes
  readiness/liveness endpoints suitable for probes or dashboards.
- Backtests emit metrics to SQLite (or JSON fallback) and store raw event logs under `runs/<id>/`.

## Testing & Tooling

- Unit tests cover the backtest engine, strategy outputs, and risk utilities (`pytest -q`).
- Formatting and linting configuration lives in `pyproject.toml` for `black`, `ruff`, and `mypy`.
- A large-scale backtest helper script (see `scripts/run_large_backtest.py`) orchestrates
  multi-core parameter sweeps for research sessions.

## Upcoming Extensions

- Plug real exchange APIs into the adapter skeletons.
- Extend the metrics registry with Prometheus exporters.
- Expand strategy suites and parameter grids for tomorrow’s heavy backtest session.
