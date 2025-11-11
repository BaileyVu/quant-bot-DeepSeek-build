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

2. Run a backtest:

```bash
make run-backtest
```

3. Run the paper trading loop (synthetic data feed):

```bash
make run-paper
```

The `.env` file controls exchange selection, credentials, and runtime flags. For Binance provide `BINANCE_API_KEY` and `BINANCE_API_SECRET`. For Hyperliquid specify `HYPERLIQUID_PK`. Set `EXCHANGE` to `binance` or `hyperliquid`, and `MODE` to `backtest`, `paper`, or `live`.

## Make targets

- `make setup` – create a virtual environment and install the project
- `make lint` – run static checks (placeholder)
- `make test` – execute the unit test suite
- `make run-backtest` – invoke the backtest CLI
- `make run-paper` – start the paper trading runner
- `make run-live` – placeholder for live mode
- `make docker-build` – build the Docker image

## Risk warning

This project is provided for educational purposes. Live trading on derivatives exchanges involves substantial risk including total capital loss. Use the paper trading mode and thoroughly test before connecting to real markets.

## Switching exchanges

Update `.env` or provide environment overrides:

```bash
EXCHANGE=hyperliquid SYMBOL=BTC python -m quantbot.live.runner --mode paper --exchange hyperliquid
```

The runtime uses exchange-specific defaults for symbols while keeping the rest of the pipeline unchanged.

