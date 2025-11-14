"""Exchange adapter interfaces and shared dataclasses."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Mapping, Protocol

from ..config import AppConfig
from ..core import OrderRequest


@dataclass(slots=True)
class SymbolMeta:
    symbol: str
    price_precision: int
    size_precision: int
    min_notional: float
    min_qty: float
    max_leverage: float
    tick_size: float
    step_size: float

    def quantize_price(self, price: float) -> float:
        rounded = round(price / self.tick_size) * self.tick_size
        return round(rounded, self.price_precision)

    def quantize_size(self, size: float) -> float:
        rounded = round(size / self.step_size) * self.step_size
        return round(rounded, self.size_precision)

    def enforce_min_notional(self, size: float, price: float) -> float:
        notional = abs(size * price)
        if notional < self.min_notional:
            factor = self.min_notional / max(price, 1e-9)
            return max(self.min_qty, round(factor, self.size_precision))
        return max(size, self.min_qty)


@dataclass(slots=True)
class AccountState:
    equity: float
    available_margin: float
    total_margin: float
    timestamp: datetime


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: float
    entry_price: float
    unrealized_pnl: float = 0.0


@dataclass(slots=True)
class PlacedOrder:
    order_id: str
    symbol: str
    status: str
    filled_qty: float
    avg_price: float
    raw: dict


class ExchangeAdapter(Protocol):
    """Abstract adapter interface implemented by concrete exchanges."""

    name: str

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        ...

    def get_account(self) -> AccountState:
        ...

    def get_positions(self) -> Mapping[str, Position]:
        ...

    def place_order(self, request: OrderRequest) -> PlacedOrder:
        ...

    def cancel_order(self, order_id: str) -> None:
        ...


class TokenBucketRateLimiter:
    """Simple token bucket limiter suitable for REST usage."""

    def __init__(self, rate_per_minute: int, burst: int) -> None:
        self.capacity = max(1, burst)
        self.tokens = float(self.capacity)
        self.refill_rate = rate_per_minute / 60.0
        self.updated_at = time.monotonic()
        self._lock = Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.updated_at = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            if self.tokens < tokens:
                deficit = tokens - self.tokens
                wait_time = deficit / max(self.refill_rate, 1e-6)
                time.sleep(wait_time)
                self.tokens = 0.0
                self.updated_at = time.monotonic()
            else:
                self.tokens -= tokens


class InMemoryExchangeState:
    """Utility for adapters that simulate fills locally."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._positions: Dict[str, Position] = {}
        self._account = AccountState(
            equity=100_000.0,
            available_margin=100_000.0,
            total_margin=100_000.0,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def update_from_fill(self, symbol: str, quantity: float, price: float, fee: float) -> None:
        position = self._positions.get(symbol, Position(symbol=symbol, quantity=0.0, entry_price=0.0))
        new_qty = position.quantity + quantity
        if abs(new_qty) < 1e-9:
            position = Position(symbol=symbol, quantity=0.0, entry_price=0.0, unrealized_pnl=0.0)
        else:
            avg_price = (position.entry_price * position.quantity + price * quantity) / new_qty if position.quantity != 0 else price
            position = Position(symbol=symbol, quantity=new_qty, entry_price=avg_price, unrealized_pnl=0.0)
        self._positions[symbol] = position
        notional = quantity * price
        self._account.equity -= notional + fee
        self._account.available_margin = self._account.equity
        self._account.total_margin = self._account.equity
        self._account.timestamp = datetime.now(tz=timezone.utc)

    def get_positions(self) -> Mapping[str, Position]:
        return dict(self._positions)

    def get_account(self) -> AccountState:
        return self._account


__all__ = [
    "ExchangeAdapter",
    "SymbolMeta",
    "AccountState",
    "Position",
    "PlacedOrder",
    "TokenBucketRateLimiter",
    "InMemoryExchangeState",
]
