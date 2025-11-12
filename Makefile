PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python

.PHONY: setup lint test run-backtest run-paper run-live docker-build

setup:
$(PYTHON) -m venv $(VENV)
$(PIP) install --upgrade pip
$(PIP) install -e .

lint:
@echo "linting not configured"

test:
$(PYTHON_BIN) -m pytest -q

run-backtest:
    CONFIG_FILE=$${CONFIG:-configs/binance_backtest.toml}; \
    SYMBOL_FLAG=$${SYMBOL:+--symbol $$SYMBOL}; \
    $(PYTHON_BIN) -m quantbot.backtest.engine --config $$CONFIG_FILE $$SYMBOL_FLAG

run-paper:
    CONFIG_FILE=$${CONFIG:-configs/binance_paper.toml}; \
    SYMBOL_FLAG=$${SYMBOL:+--symbol $$SYMBOL}; \
    EXCHANGE_FLAG=$${EXCHANGE:+--exchange $$EXCHANGE}; \
    $(PYTHON_BIN) -m quantbot.live.runner --mode paper --config $$CONFIG_FILE $$EXCHANGE_FLAG $$SYMBOL_FLAG

run-live:
    $(PYTHON_BIN) -m quantbot.live.runner --mode live --exchange $$EXCHANGE --symbol $$SYMBOL

run-status:
    $(PYTHON_BIN) -m uvicorn quantbot.api.status:app --reload --port $${PORT:-8000}

docker-build:
docker build -t quantbot:latest .
