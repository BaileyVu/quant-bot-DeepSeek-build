"""Hyperliquid perpetual adapter with the same contract as Binance."""
from __future__ import annotations

import itertools
import logging
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


class HyperliquidPerpAdapter(ExchangeAdapter):
    name = "hyperliquid-perp"

    def __init__(
        self,
        config: AppConfig,
        *,
        metadata: Mapping[str, SymbolMeta] | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        retry: object | None = None,
    ) -> None:
        self.config = config
        self._metadata: MutableMapping[str, SymbolMeta] = dict(metadata or {})
        self._state = InMemoryExchangeState(config)
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter(
            rate_per_minute=config.api.rate_limit.requests_per_minute,
            burst=config.api.rate_limit.burst,
        )
        self._id_counter = itertools.count(1)
        for symbol in config.runtime.symbols:
            self._metadata.setdefault(symbol, self._default_meta(symbol))

    def get_symbol_meta(self, symbol: str) -> SymbolMeta:
        try:
            return self._metadata[symbol]
        except KeyError:  # pragma: no cover - defensive
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
        price = meta.quantize_price(request.price or meta.tick_size * 100)
        qty = meta.quantize_size(request.quantity)
        qty = meta.enforce_min_notional(qty, price)
        side_factor = 1 if request.side == "buy" else -1
        trade_qty = qty * side_factor
        fee_rate = self.config.fees.taker_rate
        fee = abs(trade_qty * price) * fee_rate
        self._state.update_from_fill(request.symbol, trade_qty, price, fee)
        order_id = f"{self.name}-{next(self._id_counter)}"
        payload = {
            "symbol": request.symbol,
            "qty": qty,
            "price": price,
            "side": request.side,
            "reduce_only": request.reduce_only,
        }
        return PlacedOrder(
            order_id=order_id,
            symbol=request.symbol,
            status="filled",
            filled_qty=trade_qty,
            avg_price=price,
            raw=payload,
        )

    def cancel_order(self, order_id: str) -> None:  # pragma: no cover - noop
        self._rate_limiter.acquire()
        logger.info("cancel_order", extra={"_json_extras_order": {"id": order_id}})

    def _default_meta(self, symbol: str) -> SymbolMeta:
        price_precision = 1
        size_precision = 4
        tick_size = 0.5
        step_size = 0.0001
        if symbol.endswith("-PERP"):
            price_precision = 3
            tick_size = 0.01
        return SymbolMeta(
            symbol=symbol,
            price_precision=price_precision,
            size_precision=size_precision,
            min_notional=10.0,
            min_qty=0.0001,
            max_leverage=self.config.risk.max_leverage,
            tick_size=tick_size,
            step_size=step_size,
        )


__all__ = ["HyperliquidPerpAdapter"]
