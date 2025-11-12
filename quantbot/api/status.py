"""FastAPI status service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI

from ..config import get_config

app = FastAPI(title="quantbot-status")

_STATE: Dict[str, Any] = {
    "pnl": {"realized": 0.0, "unrealized": 0.0},
    "position": {},
    "params": {},
    "metrics": {},
    "ready": False,
    "reason": None,
}


def mark_ready(ready: bool, reason: str | None = None) -> None:
    _STATE["ready"] = ready
    _STATE["reason"] = reason


@app.get("/health/live")
def live() -> dict:
    return {"status": "live", "timestamp": datetime.now(tz=timezone.utc).isoformat()}


@app.get("/health/ready")
def ready() -> dict:
    cfg = get_config()
    status = "ready" if _STATE["ready"] else "blocked"
    return {
        "status": status,
        "env": cfg.environment,
        "mode": cfg.runtime.mode,
        "exchange": cfg.runtime.exchange,
        "reason": _STATE.get("reason"),
    }


@app.get("/metrics")
def metrics() -> dict:
    return {
        "pnl": _STATE["pnl"],
        "position": _STATE["position"],
        "custom": _STATE["metrics"],
    }


@app.get("/params")
def params() -> dict:
    cfg = get_config()
    return {
        "env": cfg.environment,
        "mode": cfg.runtime.mode,
        "exchange": cfg.runtime.exchange,
        "symbols": cfg.runtime.symbols,
        "bar_interval": cfg.runtime.bar_interval,
    }


def update_metrics(**metrics: Any) -> None:
    _STATE["metrics"].update(metrics)


def update_position(symbol: str, qty: float) -> None:
    _STATE["position"][symbol] = qty


def update_pnl(realized: float, unrealized: float) -> None:
    _STATE["pnl"] = {"realized": realized, "unrealized": unrealized}


__all__ = ["app", "update_metrics", "update_position", "update_pnl", "mark_ready"]
