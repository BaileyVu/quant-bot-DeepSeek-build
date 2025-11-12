# Quantbot

Quantbot is a thin, production-ready slice of a quantitative trading stack that spans from data collection to strategy execution. It supports both Binance Futures and Hyperliquid perpetuals with a unified configuration and provides entry points for research, backtesting, paper trading, and live operation.

## Features

- Unified configuration via Pydantic settings and `.env`
- Structured JSON logging with run metadata
- Event-driven backtester with funding, fees, and slippage modelling
- Momentum example strategy with leverage controls
- Paper trading loop sharing the same strategy and risk stack
- Pluggable exchange adapters for Binance Futures and Hyperliquid
- FastAPI status service exposing health and telemetry endpoints
- Docker + Makefile for consistent local and container workflows

## Quickstart

1. Install dependencies and initialise the environment:

```bash
make setup
cp .env.example .env
```

2. Run a backtest (loads settings from TOML and the environment):

```bash
python -m quantbot.backtest.engine --config configs/binance_backtest.toml
```

3. Run the paper trading loop (synthetic data feed, same risk stack):

```bash
python -m quantbot.live.runner --mode paper --config configs/binance_paper.toml
```

The `.env` file controls secrets and defaults. The following environment variables are required:

- `ENVIRONMENT` – `dev`, `staging`, or `prod` (affects logging metadata and readiness checks).
- Exchange credentials such as `BINANCE_API_KEY` / `BINANCE_API_SECRET` or `HYPERLIQUID_PK`.

Runtime specifics (mode, exchange, symbols, risk limits, data windows) live in TOML config files under `configs/` and can be overridden per invocation via CLI flags.

## Make targets

- `make setup` – create a virtual environment and install the project
- `make lint` – run static checks (placeholder)
- `make test` – execute the unit test suite
- `make run-backtest` – invoke the backtest CLI with the default config
- `make run-paper` – start the paper trading runner (synthetic feed)
- `make run-status` – launch the FastAPI status service (`uvicorn quantbot.api.status:app`)
- `make run-live` – placeholder for live mode
- `make docker-build` – build the Docker image

## Large backtest sweeps

Use `scripts/run_large_backtest.py` to launch multi-core parameter sweeps:

```bash
python scripts/run_large_backtest.py --config configs/binance_backtest.toml --fast 20 40 60 --slow 100 150 --z 1.0 1.5 --processes 8
```

Results are written to `results/backtest_sweep.csv` by default.

## Risk warning

This project is provided for educational purposes. Live trading on derivatives exchanges involves substantial risk including total capital loss. Use the paper trading mode and thoroughly test before connecting to real markets.

## Switching exchanges

Update `.env` or provide environment overrides:

```bash
EXCHANGE=hyperliquid SYMBOL=BTC python -m quantbot.live.runner --mode paper --exchange hyperliquid
```

The runtime uses exchange-specific defaults for symbols while keeping the rest of the pipeline unchanged.

