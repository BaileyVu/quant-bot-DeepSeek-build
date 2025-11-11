"""Simple z-score momentum strategy."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque

import numpy as np

from .base import Strategy, Target
from ..data.normalizer import MarketState


def _ewm(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2 / (span + 1)
    out = np.zeros_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


@dataclass
class MomentumConfig:
    fast: int = 50
    slow: int = 200
    z_clip: float = 2.0
    max_leverage: float = 2.0
    contract_value: float = 1.0


class MomentumStrategy(Strategy):
    def __init__(self, config: MomentumConfig | None = None) -> None:
        self.config = config or MomentumConfig()
        self._returns: Deque[float] = deque(maxlen=max(self.config.fast, self.config.slow) * 3)

    def on_bar(self, state: MarketState) -> Target:
        self._returns.append(state.returns)
        if len(self._returns) < max(self.config.fast, self.config.slow):
            return Target(qty=0.0)
        values = np.array(self._returns)
        fast = _ewm(values, self.config.fast)[-1]
        slow = _ewm(values, self.config.slow)[-1]
        momentum = fast - slow
        std = values.std(ddof=1) if len(values) > 1 else 0.0
        z = momentum / std if std > 0 else 0.0
        z = float(np.clip(z, -self.config.z_clip, self.config.z_clip))
        leverage = z / self.config.z_clip * self.config.max_leverage
        target_notional = leverage
        qty = target_notional * self.config.contract_value
        return Target(qty=qty)


__all__ = ["MomentumStrategy", "MomentumConfig"]
