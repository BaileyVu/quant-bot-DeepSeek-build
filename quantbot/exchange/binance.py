"""Binance Futures adapter with precision enforcement and retries."""
from __future__ import annotations

import itertools
import logging
import random
import time
from dataclasses import dataclass
from typing import Mapping, MutableMapping

from ..config import AppConfig
from ..core import OrderRequest
from .base import (
    AccountState,
    ExchangeAdapter,
    InMemoryExchangeState,
    PlacedOrder,
    Position,
    SymbolMeta,
    TokenBucketRateLimiter,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetryConfig:
    attempts: int
    backoff_seconds: float


class BinanceFuturesAdapter(ExchangeAdapter):
    name = "binance-futures"

    def __init__(
        self,
        config: AppConfig,
        *,
        metadata: Mapping[str, SymbolMeta] | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        retry: RetryConfig | None = None,
    ) -> None:
        self.config = config
        self._metadata: MutableMapping[str, SymbolMeta] = dict(metadata or {})
        self._state = InMemoryExchangeState(config)
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(
            rate_per_minute=config.api.rate_limit.requests_per_minute,
            burst=config.api.rate_limit.burst,
        )
        self._retry = retry or RetryConfig(
            attempts=config.api.max_retries,
            backoff_seconds=config.api.retry_backoff_seconds,
        )
        self._id_counter = itertools.count(1)
        for symbol in config.runtime.symbols:
            self._metadata.setdefault(symbol, self._default_meta(symbol))

    # -- ExchangeAdapter interface -------------------------------------------------
    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        try:
            return self._metadata[symbol]
        except KeyError as exc:  # pragma: no cover - defensive
            meta = self._default_meta(symbol)
            self._metadata[symbol] = meta
            return meta

    def get_account(self) -> AccountState:
        return self._state.get_account()

    def get_positions(self) -> Mapping[str, Position]:
        return self._state.get_positions()

    def place_order(self, request: OrderRequest) -> PlacedOrder:
        self._rate_limiter.acquire()
        meta = self.get_symbol_meta(request.symbol)
        qty = meta.quantize_size(request.quantity)
        if qty == 0:
            raise ValueError("order quantity rounded to zero")
        if request.price is None:
            price = meta.tick_size * round(30_000 / meta.tick_size)
        else:
            price = meta.quantize_price(request.price)
        qty = meta.enforce_min_notional(qty, price)
        for attempt in range(1, self._retry.attempts + 1):
            try:
                return self._execute_order(meta, request, qty, price)
            except (TimeoutError, ConnectionError) as exc:  # pragma: no cover - network
                sleep = self._retry.backoff_seconds * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.25 * sleep)
                logger.warning(
                    "retrying order", extra={"_json_extras_retry": {"attempt": attempt, "sleep": sleep + jitter}}
                )
                time.sleep(sleep + jitter)
        raise RuntimeError("order placement failed after retries")

    def cancel_order(self, order_id: str) -> None:  # pragma: no cover - noop in simulation
        self._rate_limiter.acquire()
        logger.info("cancel_order", extra={"_json_extras_order": {"id": order_id}})

    # -- Internal ------------------------------------------------------------------
    def _execute_order(
        self,
        meta: SymbolMeta,
        request: OrderRequest,
        qty: float,
        price: float,
    ) -> PlacedOrder:
        side_factor = 1 if request.side == "buy" else -1
        trade_qty = qty * side_factor
        fee_rate = self.config.fees.taker_rate if request.order_type != "post_only" else self.config.fees.maker_rate
        fee = abs(trade_qty * price) * fee_rate
        self._state.update_from_fill(request.symbol, trade_qty, price, fee)
        order_id = f"{self.name}-{next(self._id_counter)}"
        payload = {
            "symbol": request.symbol,
            "side": request.side,
            "qty": qty,
            "price": price,
            "type": request.order_type,
            "reduce_only": request.reduce_only,
            "post_only": request.post_only,
        }
        return PlacedOrder(
            order_id=order_id,
            symbol=request.symbol,
            status="filled",
            filled_qty=trade_qty,
            avg_price=price,
            raw=payload,
        )

    def _default_meta(self, symbol: str) -> SymbolMeta:
        price_precision = 2
        size_precision = 3
        tick_size = 0.1
        step_size = 0.001
        if symbol.endswith("USDT"):
            price_precision = 2
            tick_size = 0.1
        elif symbol.endswith("USD"):
            price_precision = 1
            tick_size = 0.5
        return SymbolMeta(
            symbol=symbol,
            price_precision=price_precision,
            size_precision=size_precision,
            min_notional=5.0,
            min_qty=0.001,
            max_leverage=self.config.risk.max_leverage,
            tick_size=tick_size,
            step_size=step_size,
        )


__all__ = ["BinanceFuturesAdapter", "RetryConfig"]
