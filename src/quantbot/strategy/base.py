"""Strategy interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..data.normalizer import MarketState


@dataclass
class Target:
    """Desired position target in base units."""

    qty: float


class Strategy(Protocol):
    """Strategy protocol."""

    def on_bar(self, state: MarketState) -> Target:
        """Return target position for given market state."""


__all__ = ["Strategy", "Target"]
