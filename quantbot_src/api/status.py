"""FastAPI status service."""
from __future__ import annotations

from fastapi import FastAPI

from ..config import get_settings

app = FastAPI(title="quantbot-status")

_state = {
    "pnl": 0.0,
    "position": 0.0,
    "params": {},
    "metrics": {},
}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/pnl")
def pnl() -> dict:
    return {"pnl": _state["pnl"]}


@app.get("/position")
def position() -> dict:
    return {"position": _state["position"]}


@app.get("/params")
def params() -> dict:
    settings = get_settings()
    return {
        "exchange": settings.exchange,
        "mode": settings.mode,
        "symbol": settings.symbol,
        "bar_interval": settings.bar_interval,
    }


@app.get("/metrics")
def metrics() -> dict:
    return _state["metrics"]


__all__ = ["app"]
