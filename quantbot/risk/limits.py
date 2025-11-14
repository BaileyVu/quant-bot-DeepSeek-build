"""Position limit checks."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig, get_config


@dataclass
class LimitResult:
    allowed: bool
    reason: str | None = None


class LimitChecker:
    def __init__(self, equity: float = 10_000.0, config: AppConfig | None = None) -> None:
        self.equity = equity
        self.config = config or get_config()

    def check_leverage(self, notional: float) -> LimitResult:
        leverage = abs(notional) / max(self.equity, 1e-9)
        max_leverage = self.config.risk.max_leverage
        if leverage > max_leverage:
            return LimitResult(False, f"leverage {leverage:.2f} exceeds {max_leverage}")
        max_notional = self.config.risk.max_order_notional
        if abs(notional) > max_notional:
            return LimitResult(False, f"notional {notional:.2f} exceeds {max_notional}")
        return LimitResult(True)


__all__ = ["LimitChecker", "LimitResult"]
