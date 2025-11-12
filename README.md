# Quantbot

Quantbot is a thin, production-ready slice of a quantitative trading stack that spans from data collection to strategy execution. It supports both Binance Futures and Hyperliquid perpetuals with a unified configuration and provides entry points for research, backtesting, paper trading, and live operation.

## Features

- Unified configuration via typed Pydantic settings (`quantbot.config`) with environment/TOML overrides
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
```

2. Set the mandatory environment flag:

```bash
export ENVIRONMENT=dev
```

3. Run a backtest (uses typed config files under `configs/`):

```bash
python -m quantbot.backtest.engine --config configs/binance_backtest.toml
```

4. Run the paper trading loop (synthetic data feed):

```bash
python -m quantbot.live.runner --mode paper --config configs/binance_paper.toml
```

Configuration is driven by the typed models in `quantbot.config`. Provide values via TOML files (see `configs/`) and/or environment variables. Critical flags:

- `ENVIRONMENT` – `dev`, `staging`, or `prod` (mandatory)
- `MODE` – `backtest`, `paper`, or `live`
- `EXCHANGE` – `binance` or `hyperliquid`
- `SYMBOL` / `RUNTIME__SYMBOLS` – primary instrument(s)

Exchange credentials are read from the `api` section (`BINANCE_API_KEY`, `BINANCE_API_SECRET`, `HYPERLIQUID_PK`).

## Make targets

- `make setup` – create a virtual environment and install the project
- `make lint` – run static checks (placeholder)
- `make test` – execute the unit test suite
- `make run-backtest` – invoke the backtest CLI (respects the active config/environment)
- `make run-paper` – start the paper trading runner
- `make run-live` – placeholder for live mode
- `make docker-build` – build the Docker image

## Risk warning

This project is provided for educational purposes. Live trading on derivatives exchanges involves substantial risk including total capital loss. Use the paper trading mode and thoroughly test before connecting to real markets.

## Switching exchanges

Update `.env` or provide environment overrides:

```bash
ENVIRONMENT=staging python -m quantbot.live.runner --mode paper --exchange hyperliquid --symbol BTC-PERP --config configs/hyperliquid_backtest.toml
```

The runtime uses exchange-specific defaults for symbols while keeping the rest of the pipeline unchanged.

## Large backtest sweeps

Use the helper script to launch multi-core parameter grids:

```bash
ENVIRONMENT=dev python scripts/run_large_backtest.py --config configs/binance_backtest.toml --fast 10,20,30 --slow 60,90,120 --z-clip 1.5,2.0,2.5 --bars 5000
```

Results (Sharpe, drawdown, hit rate, final equity) are written to `results/backtest_grid.csv` sorted by Sharpe ratio.

