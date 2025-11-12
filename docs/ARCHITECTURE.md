# Quant Bot Architecture Overview

This document captures the current package layout, primary entrypoints, and runtime flows after the safety and infrastructure refactor.

## Package Layout

The codebase follows a src layout (`src/quantbot`). Key modules:

- `config/` – Typed Pydantic configuration models (`models.py`), the `Settings` wrapper (`settings.py`), and loader helpers (`loader.py`).
- `data/` – Market data abstractions and event models shared across modes (`normalizer.py`, `events.py`, `sources.py`).
- `backtest/` – Event-driven backtest engine (`engine.py`), historical dataset helpers (`datasets.py`), and analytics (`metrics.py`).
- `live/` – Paper/live runner (`runner.py`) and liveness heartbeat utility.
- `exchange/` – Unified exchange adapter models and in-memory Binance / Hyperliquid implementations (`binance.py`, `hyperliquid.py`, `models.py`, `base.py`).
- `risk/` – Funding, limit helpers, and the new centralized `RiskManager` (`manager.py`).
- `strategy/` – Strategy protocol (`base.py`) and the default `MomentumStrategy` implementation.
- `telemetry/` – Lightweight metrics registry used by the FastAPI status service and engines.
- `api/status.py` – FastAPI app exposing health and metrics endpoints.
- `logging_setup.py` – Structured JSON logging configured with environment/exchange metadata.

## Entrypoints

- **Backtesting** – `python -m quantbot.backtest.engine --config configs/binance_backtest.toml` or `make run-backtest` (see README). The `BacktestEngine` constructs shared events, runs strategies, gates orders through the `RiskManager`, writes replay logs, and updates metrics.
- **Paper trading** – `python -m quantbot.live.runner --mode paper --config configs/binance_paper.toml`. Uses the same event flow as backtests, with adapters simulating exchange fills.
- **Live trading** – The runner is structured for live integration; swap the adapter with a real network implementation when credentials are configured.
- **Status service** – `uvicorn quantbot.api.status:app`. Provides `/health/live`, `/health/ready`, `/metrics`, and `/config` endpoints sourcing configuration and runtime metrics.

## Strategies & Risk Flow

Strategies implement `Strategy.on_bar(MarketState) -> Target`. The backtest/paper loops convert targets to `OrderRequest` objects, which pass through the `RiskManager`. The manager enforces per-order notional, leverage, daily loss/drawdown limits, data quality thresholds, and kill switch checks. Approved orders are quantized via `SymbolMeta` before execution through adapters.

## Exchange Adapters

`exchange.base.ExchangeAdapter` defines the contract shared by Binance and Hyperliquid implementations. Adapters handle precision, simple rate limiting, retries, and maintain in-memory account/position state for simulations. All order creation routes through `SymbolMeta` helpers to enforce tick/lot sizes and minimum notionals.

## Configuration & Environments

Configuration is layered: defaults → optional TOML file → environment variables. Required environment variables include `ENVIRONMENT` (`dev|staging|prod`). Nested config sections cover runtime, risk, data, execution, and API credentials. Sample TOML configurations live in `configs/`.

## Observability

Structured JSON logging includes environment/mode/exchange/symbol metadata and a run identifier. The metrics registry tracks order counts, gauges (equity, position), and basic latency placeholders. The FastAPI service exposes snapshots for dashboards and readiness checks (including kill switch state).

