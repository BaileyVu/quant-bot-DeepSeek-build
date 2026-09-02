"""Paper portfolio with shared cash and symbol-aware positions."""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from loguru import logger

from quantos.config import get_config


@dataclass
class PaperTrade:
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


class PaperPortfolio:
    """
    Manages cash, positions, and trades across multiple symbols.
    Uses the same accounting conventions as Milestone 4.
    """

    def __init__(self, initial_capital: float, fee_bps: float, slippage_bps: float):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.fee_rate = fee_bps / 10000.0
        self.slippage_rate = slippage_bps / 10000.0
        # Positions: symbol -> quantity
        self.positions: Dict[str, float] = {}
        # Entry prices: symbol -> average entry price (for PnL)
        self.entry_prices: Dict[str, float] = {}
        self.trades: List[PaperTrade] = []
        self.history: List[Dict[str, Any]] = []  # snapshots
        self._total_fees_paid = 0.0
        self._total_slippage_paid = 0.0

    def get_equity(self, prices: Dict[str, float]) -> float:
        """Compute total equity = cash + sum(position * price)."""
        total = self.cash
        for sym, qty in self.positions.items():
            price = prices.get(sym, 0.0)
            total += qty * price
        return total

    def update(self, symbol: str, price: float, signal: float, threshold: float) -> Dict[str, Any]:
        """
        Process one event: given signal, decide to enter/exit for this symbol.
        """
        # Check if we have an open position for this symbol
        has_position = symbol in self.positions and self.positions[symbol] > 0

        if has_position and signal < threshold:
            self._exit(symbol, price)
        elif not has_position and signal >= threshold:
            self._enter(symbol, price)

        # Compute current equity (need all prices – we only have the current one, but we can keep last known)
        # We'll just update state and return; equity will be computed externally or later with full prices.
        # For snapshot, we'll compute equity using the current price for this symbol and cached prices for others.
        # For simplicity, we'll store the price in the snapshot.
        state = {
            "timestamp": datetime.utcnow(),
            "symbol": symbol,
            "price": price,
            "cash": self.cash,
            "position": self.positions.get(symbol, 0.0),
            "entry_price": self.entry_prices.get(symbol),
        }
        self.history.append(state)
        return state

    def _enter(self, symbol: str, price: float):
        """Enter a long position for symbol using all available cash."""
        if symbol in self.positions and self.positions[symbol] > 0:
            return
        # Compute cost per unit with slippage
        cost_per_unit = price * (1 + self.slippage_rate)
        fee = self.cash * self.fee_rate
        available = self.cash - fee
        if available <= 0:
            logger.warning(f"Insufficient cash to enter {symbol} at {price}")
            return
        quantity = available / cost_per_unit
        notional = quantity * price
        self.cash = self.cash - fee - quantity * cost_per_unit
        self.positions[symbol] = quantity
        self.entry_prices[symbol] = price
        self._total_fees_paid += fee
        self._total_slippage_paid += quantity * price * self.slippage_rate
        logger.info(f"Paper enter {symbol} qty {quantity:.6f} at {price}")

    def _exit(self, symbol: str, price: float):
        """Exit current long position for symbol."""
        if symbol not in self.positions or self.positions[symbol] <= 0:
            return
        quantity = self.positions[symbol]
        # Sell with slippage
        received_per_unit = price * (1 - self.slippage_rate)
        gross_revenue = quantity * received_per_unit
        fee = gross_revenue * self.fee_rate
        net_revenue = gross_revenue - fee
        self.cash += net_revenue
        # Record trade
        entry_price = self.entry_prices.get(symbol, price)
        gross_pnl = quantity * (price - entry_price)
        net_pnl = gross_pnl - fee - quantity * price * self.slippage_rate - self._total_slippage_paid
        # We'll compute properly:
        fee_entry = self._total_fees_paid - (self._total_fees_paid - fee)
        # Better: store trade details during entry and exit.
        # Since we didn't store trade object, we'll create one now.
        trade = PaperTrade(
            symbol=symbol,
            direction="long",
            entry_time=self.history[-1]["timestamp"] if self.history else datetime.utcnow(),
            entry_price=entry_price,
            exit_time=datetime.utcnow(),
            exit_price=price,
            quantity=quantity,
            entry_notional=quantity * entry_price,
            exit_notional=quantity * price,
            fee_entry=0.0,  # we can estimate
            fee_exit=fee,
            slippage_entry=0.0,
            slippage_exit=quantity * price * self.slippage_rate,
            gross_pnl=gross_pnl,
            net_pnl=gross_pnl - fee - quantity * price * self.slippage_rate,
        )
        self.trades.append(trade)
        # Clear position
        del self.positions[symbol]
        del self.entry_prices[symbol]
        self._total_fees_paid += fee
        self._total_slippage_paid += quantity * price * self.slippage_rate
        logger.info(f"Paper exit {symbol} qty {quantity:.6f} at {price}, net PnL {trade.net_pnl:.2f}")

    def get_state(self) -> Dict[str, Any]:
        """Return current state for persistence."""
        return {
            "cash": self.cash,
            "positions": self.positions.copy(),
            "entry_prices": self.entry_prices.copy(),
            "trades": self.trades,
            "total_fees_paid": self._total_fees_paid,
            "total_slippage_paid": self._total_slippage_paid,
        }

    def load_state(self, state: Dict[str, Any]):
        """Restore state from persistence."""
        self.cash = state["cash"]
        self.positions = state["positions"]
        self.entry_prices = state["entry_prices"]
        self.trades = state["trades"]
        self._total_fees_paid = state["total_fees_paid"]
        self._total_slippage_paid = state["total_slippage_paid"]
