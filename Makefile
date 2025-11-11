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
$(PYTHON_BIN) -m quantbot.backtest.engine --symbol $$SYMBOL

run-paper:
$(PYTHON_BIN) -m quantbot.live.runner --mode paper --exchange $$EXCHANGE --symbol $$SYMBOL

run-live:
$(PYTHON_BIN) -m quantbot.live.runner --mode live --exchange $$EXCHANGE --symbol $$SYMBOL

docker-build:
docker build -t quantbot:latest .
