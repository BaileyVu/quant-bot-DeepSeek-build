"""Binance Futures exchange adapter."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict

from ..config import Settings
from ..utils.time import utc_now
from .base import PrecisionMixin, RateLimiter
from .models import AccountState, OrderRequest, PlacedOrder, Position, Side, SymbolMeta


@dataclass(slots=True)
class _SymbolPreset:
    price_precision: int
    size_precision: int
    tick_size: float
    step_size: float
    min_notional: float
    max_leverage: float


_DEFAULT_PRESETS: Dict[str, _SymbolPreset] = {
    "BTCUSDT": _SymbolPreset(2, 3, 0.1, 0.001, 5.0, 50.0),
    "ETHUSDT": _SymbolPreset(2, 2, 0.01, 0.01, 5.0, 40.0),
}


class BinanceFuturesAdapter(PrecisionMixin):
    name = "binance"

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        api = settings.api_for_exchange(self.name)
        self._rate_limiter = RateLimiter(api.rate_limit_per_minute)
        self._account = AccountState(equity=10_000.0, available_balance=10_000.0, timestamp=utc_now())
        self._positions: Dict[str, Position] = {}
        self._order_id = 0
        self._lock = asyncio.Lock()

    async def _fetch_symbol_meta(self, symbol: str) -> SymbolMeta:
        preset = _DEFAULT_PRESETS.get(symbol.upper())
        if not preset:
            preset = _DEFAULT_PRESETS["BTCUSDT"]
        return SymbolMeta(
            symbol=symbol.upper(),
            price_precision=preset.price_precision,
            size_precision=preset.size_precision,
            tick_size=preset.tick_size,
            step_size=preset.step_size,
            min_notional=preset.min_notional,
            max_leverage=preset.max_leverage,
        )

    async def get_account(self) -> AccountState:
        await self._rate_limiter.acquire()
        return self._account

    async def get_positions(self) -> Dict[str, Position]:
        await self._rate_limiter.acquire()
        return dict(self._positions)

    async def place_order(self, request: OrderRequest) -> PlacedOrder:
        async with self._lock:
            await self._rate_limiter.acquire()
            price, qty = await self.quantized(request.symbol, request.price, request.qty)
            side_multiplier = 1 if request.side == "buy" else -1
            position = self._positions.get(request.symbol)
            entry_ref = price or 0.0
            if position:
                new_qty = position.qty + qty * side_multiplier
                position.qty = new_qty
                if price:
                    position.entry_price = price
                entry_ref = position.entry_price
            else:
                self._positions[request.symbol] = Position(
                    symbol=request.symbol,
                    qty=qty * side_multiplier,
                    entry_price=entry_ref,
                )
            notional = abs(qty * (price or entry_ref))
            fee_rate = self.settings.execution.taker_fee_bps / 10_000
            fee = notional * fee_rate
            self._account.available_balance -= fee
            self._account.equity -= fee
            self._account.timestamp = utc_now()
            self._order_id += 1
            order_id = f"BNF-{self._order_id}"
            return PlacedOrder(
                order_id=order_id,
                symbol=request.symbol,
                side=request.side,
                type=request.type,
                qty=qty,
                price=price,
                status="filled",
                client_order_id=request.client_order_id,
                meta={"fee": fee},
            )

    async def cancel_order(self, order_id: str) -> None:  # pragma: no cover - no outstanding orders in tests
        await self._rate_limiter.acquire()
        return None


__all__ = ["BinanceFuturesAdapter"]
