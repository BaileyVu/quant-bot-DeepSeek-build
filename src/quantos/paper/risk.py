"""Risk checks for paper trading."""

from typing import Dict, Optional
from loguru import logger

from quantos.config import get_config


class RiskEngine:
    def __init__(self):
        self.config = get_config().paper
        self.initial_capital = self.config.initial_capital
        self.max_position_notional = self.config.max_position_notional
        self.max_daily_loss_pct = self.config.max_daily_loss_pct
        self.max_drawdown_pct = self.config.max_drawdown_pct
        self.daily_loss = 0.0
        self.peak_equity = self.initial_capital
        self.last_reset_date = None

    def check_order(self, symbol: str, price: float, quantity: float, current_equity: float, current_positions: Dict[str, float]) -> bool:
        """
        Check if an order (entry) passes risk limits.
        """
        # Notional check
        notional = quantity * price
        if notional > self.max_position_notional:
            logger.warning(f"Risk reject: notional {notional:.2f} exceeds max {self.max_position_notional}")
            return False

        # Daily loss check (we track daily realized PnL separately; for simplicity, we check if daily loss exceeded)
        # We'll implement a simpler version: check drawdown from peak
        if current_equity < self.peak_equity:
            drawdown_pct = (self.peak_equity - current_equity) / self.peak_equity * 100
            if drawdown_pct > self.max_drawdown_pct:
                logger.warning(f"Risk reject: drawdown {drawdown_pct:.2f}% exceeds max {self.max_drawdown_pct}%")
                return False

        # Position concentration? not needed

        return True

    def update_metrics(self, current_equity: float):
        """Update peak equity for drawdown tracking."""
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity