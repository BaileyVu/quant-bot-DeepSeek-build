"""FastAPI status service."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI

from ..config import get_settings
from ..telemetry.metrics import metrics

app = FastAPI(title="quantbot-status")


def _kill_switch_active() -> bool:
    settings = get_settings()
    kill_file = settings.risk.kill_switch_file
    return bool(kill_file and Path(kill_file).exists())


@app.get("/health/live")
def health_live() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, Any]:
    settings = get_settings()
    kill_active = _kill_switch_active()
    status = "ok" if not kill_active else "halted"
    return {
        "status": status,
        "environment": settings.environment,
        "mode": settings.mode,
        "exchange": settings.exchange,
        "symbols": settings.symbols,
        "kill_switch": kill_active,
    }


@app.get("/metrics")
def metrics_snapshot() -> dict[str, Any]:
    return metrics.snapshot()


@app.get("/config")
def config_info() -> dict[str, Any]:
    settings = get_settings()
    return {
        "environment": settings.environment,
        "runtime": settings.runtime.model_dump(),
        "risk": settings.risk.model_dump(),
        "data": settings.data.model_dump(),
    }


__all__ = ["app"]
