"""Centralised risk management."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Mapping

from ..config import Settings
from ..data.normalizer import MarketState
from ..exchange.models import AccountState, OrderRequest, Position, SymbolMeta
from ..utils.time import utc_now


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    order: OrderRequest | None = None
    reason: str | None = None
    metadata: Dict[str, float | str] = field(default_factory=dict)


class RiskManager:
    """Evaluate orders, PnL and connectivity to gate trading."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config = settings.risk
        self._start_equity: float | None = None
        self._start_day: date | None = None
        self._peak_equity: float | None = None
        self._halted: bool = False
        self._halt_reason: str | None = None
        self._consecutive_errors = 0
        self._last_price: Dict[str, float] = {}
        self._last_market_ts: Dict[str, datetime] = {}

    def is_trading_allowed(self) -> bool:
        if self._halted:
            return False
        kill_file = self.config.kill_switch_file
        if kill_file and Path(kill_file).exists():
            self.halt(f"kill switch file present at {kill_file}")
            return False
        if self._consecutive_errors >= self.config.max_consecutive_errors:
            self.halt("too many consecutive adapter errors")
            return False
        return True

    def halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason

    def clear_errors(self) -> None:
        self._consecutive_errors = 0

    def register_error(self) -> None:
        self._consecutive_errors += 1

    def register_market_state(self, symbol: str, state: MarketState) -> None:
        self._last_market_ts[symbol] = state.time
        self._last_price[symbol] = state.mid

    def _check_data_health(self, symbol: str, state: MarketState) -> tuple[bool, str | None]:
        now = utc_now()
        lag = (now - state.time).total_seconds()
        if lag > self.config.max_data_lag_seconds:
            return False, f"market data lag {lag:.1f}s exceeds {self.config.max_data_lag_seconds}s"
        spread_bps = (state.spread / max(state.mid, 1e-9)) * 10_000
        if spread_bps > self.config.max_spread_bps:
            return False, f"spread {spread_bps:.1f}bps exceeds {self.config.max_spread_bps}bps"
        last_price = self._last_price.get(symbol)
        if last_price:
            jump_bps = abs((state.mid / last_price) - 1.0) * 10_000
            if jump_bps > self.config.max_price_jump_bps:
                return False, f"price jump {jump_bps:.1f}bps exceeds {self.config.max_price_jump_bps}bps"
        return True, None

    def _update_daily_state(self, equity: float, timestamp: datetime) -> None:
        trading_day = timestamp.date()
        if self._start_day != trading_day:
            self._start_day = trading_day
            self._start_equity = equity
            self._peak_equity = equity
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

    def _check_drawdowns(self, equity: float) -> tuple[bool, str | None]:
        if self._start_equity is None or self._peak_equity is None:
            return True, None
        daily_floor = self._start_equity * (1 - self.config.max_daily_loss)
        if equity <= daily_floor:
            return False, "daily loss limit reached"
        drawdown = 0.0
        if self._peak_equity > 0:
            drawdown = (equity / self._peak_equity) - 1.0
        if drawdown <= -self.config.max_drawdown:
            return False, "max drawdown reached"
        return True, None

    def validate_order(
        self,
        request: OrderRequest,
        account_state: AccountState,
        positions: Mapping[str, Position],
        market_state: MarketState,
        symbol_meta: SymbolMeta,
    ) -> RiskDecision:
        if not self.is_trading_allowed():
            return RiskDecision(False, reason=self._halt_reason)

        self._update_daily_state(account_state.equity, account_state.timestamp)
        healthy, reason = self._check_data_health(request.symbol, market_state)
        if not healthy:
            return RiskDecision(False, reason=reason)
        drawdown_ok, reason = self._check_drawdowns(account_state.equity)
        if not drawdown_ok:
            self.halt(reason or "risk halt")
            return RiskDecision(False, reason=reason)

        price = request.price or market_state.mid
        q_price = symbol_meta.quantize_price(price)
        q_qty = symbol_meta.quantize_size(abs(request.qty))
        if q_qty == 0:
            return RiskDecision(False, reason="order size rounds to zero")
        symbol_meta.enforce_min_notional(q_qty, q_price)
        side_multiplier = 1 if request.side == "buy" else -1
        existing = positions.get(request.symbol)
        current_qty = existing.qty if existing else 0.0
        new_qty = current_qty + side_multiplier * q_qty
        if new_qty > 0 and not self.config.allow_long:
            return RiskDecision(False, reason="long positions disabled")
        if new_qty < 0 and not self.config.allow_short:
            return RiskDecision(False, reason="short positions disabled")

        per_order_notional = abs(q_qty * q_price)
        if per_order_notional > self.config.max_per_order_notional:
            return RiskDecision(False, reason="per-order notional exceeds limit")

        # Aggregate risk
        symbol_mid = market_state.mid
        existing_notional = sum(
            abs(pos.qty) * (abs(pos.entry_price) if pos.entry_price else symbol_mid)
            for pos in positions.values()
        )
        if existing:
            existing_notional -= abs(existing.qty) * (abs(existing.entry_price) if existing.entry_price else symbol_mid)
        total_notional = existing_notional + abs(new_qty) * (price or symbol_mid)
        if total_notional > self.config.max_position_notional:
            return RiskDecision(False, reason="position notional exceeds limit")
        leverage = total_notional / max(account_state.equity, 1e-9)
        if leverage > self.config.max_leverage or symbol_meta.max_leverage < leverage:
            return RiskDecision(False, reason="leverage exceeds limit")

        # Open positions count limit
        open_positions = sum(1 for pos in positions.values() if abs(pos.qty) > 1e-9)
        if abs(new_qty) > 1e-9 and current_qty == 0:
            open_positions += 1
        if open_positions > self.config.max_open_positions:
            return RiskDecision(False, reason="max open positions exceeded")

        adjusted = OrderRequest(
            symbol=request.symbol,
            side=request.side,
            type=request.type,
            qty=q_qty,
            price=q_price if request.price is not None else None,
            reduce_only=request.reduce_only,
            client_order_id=request.client_order_id,
        )
        self.register_market_state(request.symbol, market_state)
        return RiskDecision(True, order=adjusted, metadata={"leverage": leverage})

    def on_fill(self, symbol: str, qty: float) -> None:
        if abs(qty) < 1e-9:
            return
        self.clear_errors()

    def on_pnl_update(self, equity: float, timestamp: datetime) -> None:
        self._update_daily_state(equity, timestamp)
        drawdown_ok, reason = self._check_drawdowns(equity)
        if not drawdown_ok and reason:
            self.halt(reason)


__all__ = ["RiskManager", "RiskDecision"]
