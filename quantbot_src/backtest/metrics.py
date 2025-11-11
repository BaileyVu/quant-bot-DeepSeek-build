"""Backtest performance metrics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class EquityPoint:
    timestamp: int
    equity: float


def compute_metrics(equity_curve: list[EquityPoint]) -> Dict[str, float]:
    values = np.array([p.equity for p in equity_curve], dtype=float)
    returns = np.diff(values) / values[:-1]
    if len(returns) == 0:
        returns = np.array([0.0])
    mean = float(np.mean(returns))
    std = float(np.std(returns))
    sharpe = mean / std * np.sqrt(365 * 24 * 60) if std > 0 else 0.0
    drawdowns = np.maximum.accumulate(values) - values
    max_dd = float(np.max(drawdowns))
    hit_rate = float(np.mean(returns > 0))
    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "hit_rate": hit_rate,
        "return": float(values[-1] / values[0] - 1),
    }


__all__ = ["EquityPoint", "compute_metrics"]
