"""Portfolio simulator for backtesting with symbol isolation."""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from quantos.config import get_config


@dataclass
class Trade:
    symbol: str
    direction: str  # "long" only
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime]
    exit_price: Optional[float]
    quantity: float
    entry_notional: float
    exit_notional: float
    fee_entry: float
    fee_exit: float
    slippage_entry: float
    slippage_exit: float
    gross_pnl: float
    net_pnl: float


class PortfolioSimulator:
    """
    Simulates a long‑only portfolio for a single symbol with transaction costs.
    """

    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        fee_bps: float,
        slippage_bps: float,
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.fee_rate = fee_bps / 10000.0
        self.slippage_rate = slippage_bps / 10000.0
        self.reset()

    def reset(self):
        self.cash = self.initial_capital
        self.position = 0.0          # quantity of base asset (e.g., BTC)
        self.entry_price = None
        self.trade_open = False
        self.current_trade: Optional[Trade] = None
        self.history: List[Dict[str, Any]] = []   # snapshots
        self.trades: List[Trade] = []
        self._total_fees_paid = 0.0
        self._total_slippage_paid = 0.0

    def update(self, timestamp: datetime, price: float, signal: float) -> Dict[str, Any]:
        """
        Process one step: given signal (probability), decide to enter/exit.
        Returns a dictionary with current state.
        """
        threshold = get_config().backtest.signal_threshold

        if self.trade_open:
            if signal < threshold:
                self._exit(timestamp, price)
        else:
            if signal >= threshold:
                self._enter(timestamp, price)

        # Update equity with current price
        equity = self.cash + self.position * price
        state = {
            "timestamp": timestamp,
            "symbol": self.symbol,
            "cash": self.cash,
            "position": self.position,
            "price": price,
            "equity": equity,
            "trade_open": self.trade_open,
            "entry_price": self.entry_price,
        }
        self.history.append(state)
        return state

    def _enter(self, timestamp: datetime, price: float):
        """Enter a long position using all available cash."""
        if self.trade_open:
            return
        # Compute cost per unit with slippage
        cost_per_unit = price * (1 + self.slippage_rate)
        # Fee on the cash used
        fee = self.cash * self.fee_rate
        available = self.cash - fee
        if available <= 0:
            logger.warning(f"Insufficient cash to enter at {timestamp}")
            return
        quantity = available / cost_per_unit
        # Notional
        notional = quantity * cost_per_unit
        self.trade_open = True
        self.position = quantity
        self.entry_price = price
        self.cash = self.cash - fee - quantity * cost_per_unit
        self.current_trade = Trade(
            symbol=self.symbol,
            direction="long",
            entry_time=timestamp,
            entry_price=price,
            exit_time=None,
            exit_price=None,
            quantity=quantity,
            entry_notional=quantity * price,
            exit_notional=0.0,
            fee_entry=fee,
            fee_exit=0.0,
            slippage_entry=quantity * price * self.slippage_rate,
            slippage_exit=0.0,
            gross_pnl=0.0,
            net_pnl=0.0,
        )
        self._total_fees_paid += fee
        self._total_slippage_paid += quantity * price * self.slippage_rate
        logger.debug(f"Enter long {self.symbol} at {timestamp} price {price:.2f}, qty {quantity:.6f}")

    def _exit(self, timestamp: datetime, price: float):
        """Exit current long position."""
        if not self.trade_open:
            return
        quantity = self.position
        # Sell at price with slippage
        received_per_unit = price * (1 - self.slippage_rate)
        gross_revenue = quantity * received_per_unit
        fee = gross_revenue * self.fee_rate
        net_revenue = gross_revenue - fee
        self.cash += net_revenue
        # Record trade
        if self.current_trade:
            self.current_trade.exit_time = timestamp
            self.current_trade.exit_price = price
            self.current_trade.exit_notional = quantity * price
            self.current_trade.fee_exit = fee
            self.current_trade.slippage_exit = quantity * price * self.slippage_rate
            self.current_trade.gross_pnl = quantity * (price - self.current_trade.entry_price)
            self.current_trade.net_pnl = (
                self.current_trade.gross_pnl
                - self.current_trade.fee_entry
                - self.current_trade.fee_exit
                - self.current_trade.slippage_entry
                - self.current_trade.slippage_exit
            )
            self.trades.append(self.current_trade)
            self.current_trade = None
        self.position = 0.0
        self.trade_open = False
        self.entry_price = None
        logger.debug(f"Exit long {self.symbol} at {timestamp} price {price:.2f}")

    def get_final_state(self) -> Dict[str, Any]:
        """Return final portfolio metrics and trade list."""
        if self.trade_open and self.history:
            last_state = self.history[-1]
            self._exit(last_state["timestamp"], last_state["price"])
        final_equity = self.history[-1]["equity"] if self.history else self.initial_capital
        equity_curve = pd.DataFrame([
            {"timestamp": s["timestamp"], "equity": s["equity"]}
            for s in self.history
        ]) if self.history else pd.DataFrame()
        return {
            "initial_capital": self.initial_capital,
            "final_equity": final_equity,
            "total_return_pct": (final_equity / self.initial_capital - 1) * 100,
            "num_trades": len(self.trades),
            "trades": self.trades,
            "equity_curve": equity_curve,
            "total_fees_paid": self._total_fees_paid,
            "total_slippage_paid": self._total_slippage_paid,
        }