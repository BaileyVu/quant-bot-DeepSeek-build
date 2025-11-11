"""Position limit checks."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import get_settings


@dataclass
class LimitResult:
    allowed: bool
    reason: str | None = None


class LimitChecker:
    def __init__(self, equity: float = 10_000.0) -> None:
        self.equity = equity
        self.settings = get_settings()

    def check_leverage(self, notional: float) -> LimitResult:
        leverage = abs(notional) / max(self.equity, 1e-9)
        if leverage > self.settings.max_leverage:
            return LimitResult(False, f"leverage {leverage:.2f} exceeds {self.settings.max_leverage}")
        if abs(notional) > self.settings.max_notional:
            return LimitResult(False, f"notional {notional:.2f} exceeds {self.settings.max_notional}")
        return LimitResult(True)


__all__ = ["LimitChecker", "LimitResult"]
