"""Stop logic including daily kill switch."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..config import AppConfig, get_config


def pct_change(current: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return (current - reference) / reference


@dataclass
class StopState:
    equity_start: float
    kill_triggered: bool = False
    day: date | None = None


class StopManager:
    def __init__(self, starting_equity: float, config: AppConfig | None = None) -> None:
        self.config = config or get_config()
        self.state = StopState(equity_start=starting_equity, day=date.today())

    def check_daily(self, current_equity: float) -> bool:
        """Return True if trading should continue."""

        today = date.today()
        if self.state.day != today:
            self.state = StopState(equity_start=current_equity, day=today)
        drawdown = pct_change(current_equity, self.state.equity_start)
        if drawdown <= -self.config.risk.max_daily_loss:
            self.state.kill_triggered = True
        return not self.state.kill_triggered

    def check_stop(self, entry_price: float, current_price: float, stop_pct: float) -> bool:
        move = pct_change(current_price, entry_price)
        return move <= -abs(stop_pct)


__all__ = ["StopManager", "pct_change"]
