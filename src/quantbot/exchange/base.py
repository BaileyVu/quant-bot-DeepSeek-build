"""Exchange adapter interfaces and helpers."""
from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from typing import Dict, Mapping, Protocol

from .models import AccountState, OrderRequest, PlacedOrder, Position, Side, SymbolMeta


class RetryableError(Exception):
    """Error raised when a request can be retried."""


class FatalExchangeError(Exception):
    """Error raised when a request should not be retried."""


class ExchangeAdapter(Protocol):
    name: str

    async def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        ...

    async def get_account(self) -> AccountState:
        ...

    async def get_positions(self) -> Dict[str, Position]:
        ...

    async def place_order(self, request: OrderRequest) -> PlacedOrder:
        ...

    async def cancel_order(self, order_id: str) -> None:
        ...

    def quantize_price(self, symbol: str, price: float) -> float:
        ...

    def quantize_size(self, symbol: str, size: float) -> float:
        ...

    def enforce_min_notional(self, symbol: str, size: float, price: float) -> None:
        ...


class RateLimiter:
    """Token bucket style limiter suitable for REST APIs."""

    def __init__(self, rate_per_minute: int) -> None:
        self._capacity = max(rate_per_minute, 1)
        self._tokens = float(self._capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while self._tokens < 1.0:
                await self._refill()
                await asyncio.sleep(0.01)
            self._tokens -= 1.0

    async def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill_rate = self._capacity / 60.0
        self._tokens = min(self._capacity, self._tokens + elapsed * refill_rate)
        self._last_refill = now


class BackoffPolicy:
    """Exponential backoff with jitter."""

    def __init__(self, base: float = 0.2, factor: float = 2.0, max_delay: float = 5.0) -> None:
        self.base = base
        self.factor = factor
        self.max_delay = max_delay

    async def sleep(self, attempt: int) -> None:
        delay = min(self.max_delay, self.base * (self.factor**attempt))
        jitter = random.uniform(0, delay / 2)
        await asyncio.sleep(delay + jitter)


class PrecisionMixin(ABC):
    """Utility mixin to provide precision helpers based on symbol metadata."""

    def __init__(self) -> None:
        self._meta_cache: Dict[str, SymbolMeta] = {}

    async def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        if symbol not in self._meta_cache:
            self._meta_cache[symbol] = await self._fetch_symbol_meta(symbol)
        return self._meta_cache[symbol]

    @abstractmethod
    async def _fetch_symbol_meta(self, symbol: str) -> SymbolMeta:
        ...

    async def quantized(self, symbol: str, price: float | None, size: float) -> tuple[float | None, float]:
        meta = await self.get_symbol_meta(symbol)
        q_size = meta.quantize_size(size)
        q_price = meta.quantize_price(price) if price is not None else None
        if q_price is not None:
            meta.enforce_min_notional(q_size, q_price)
        return q_price, q_size

    def quantize_price(self, symbol: str, price: float) -> float:
        meta = self._meta_cache[symbol]
        return meta.quantize_price(price)

    def quantize_size(self, symbol: str, size: float) -> float:
        meta = self._meta_cache[symbol]
        return meta.quantize_size(size)

    def enforce_min_notional(self, symbol: str, size: float, price: float) -> None:
        meta = self._meta_cache[symbol]
        meta.enforce_min_notional(size, price)


async def retry_call(
    func,
    *args,
    retries: int = 3,
    backoff: BackoffPolicy | None = None,
    retry_exceptions: tuple[type[Exception], ...] = (RetryableError,),
    **kwargs,
):
    """Invoke ``func`` with retries."""

    backoff = backoff or BackoffPolicy()
    attempt = 0
    while True:
        try:
            return await func(*args, **kwargs)
        except retry_exceptions:
            if attempt >= retries:
                raise
            await backoff.sleep(attempt)
            attempt += 1


__all__ = [
    "ExchangeAdapter",
    "RateLimiter",
    "PrecisionMixin",
    "RetryableError",
    "FatalExchangeError",
    "retry_call",
]
