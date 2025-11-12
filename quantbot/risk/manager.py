"""Centralised risk management and kill switch logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Mapping

from ..config import AppConfig
from ..core import OrderRequest
from ..data import MarketState
from ..exchange import AccountState, Position


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason: str | None = None
    adjusted_order: OrderRequest | None = None


@dataclass
class RiskState:
    start_equity: float = 0.0
    peak_equity: float = 0.0
    day: date | None = None
    kill_triggered: bool = False
    kill_reason: str | None = None


class RiskManager:
    """Evaluate orders against global risk constraints."""

    def __init__(
        self,
        config: AppConfig,
        *,
        kill_switch_file: Path | None = Path("state/kill_switch"),
        max_adapter_errors: int = 5,
        max_data_lag: timedelta = timedelta(minutes=5),
        max_spread_bps: float = 75.0,
    ) -> None:
        self.config = config
        self.kill_switch_file = kill_switch_file
        self.max_adapter_errors = max_adapter_errors
        self.max_data_lag = max_data_lag
        self.max_spread_bps = max_spread_bps
        self.state = RiskState()
        self.adapter_errors = 0
        self.last_market_time: datetime | None = None
        self.positions: Dict[str, Position] = {}

    # ------------------------------------------------------------------
    def is_trading_allowed(self) -> bool:
        if self.state.kill_triggered:
            return False
        if self.kill_switch_file and self.kill_switch_file.exists():
            self.state.kill_triggered = True
            self.state.kill_reason = "manual override"
            return False
        if self.adapter_errors >= self.max_adapter_errors:
            self.state.kill_triggered = True
            self.state.kill_reason = "adapter error threshold"
            return False
        if self.last_market_time and datetime.now(tz=timezone.utc) - self.last_market_time > self.max_data_lag:
            self.state.kill_triggered = True
            self.state.kill_reason = "market data stale"
            return False
        return True

    def validate_order(
        self,
        request: OrderRequest,
        market_state: MarketState,
        account: AccountState,
        positions: Mapping[str, Position] | None = None,
    ) -> RiskDecision:
        if not self.is_trading_allowed():
            return RiskDecision(False, reason=self.state.kill_reason)
        positions = positions or {}
        symbol = request.symbol
        meta = positions.get(symbol)
        current_qty = meta.quantity if meta else 0.0
        future_qty = current_qty + (request.quantity if request.side == "buy" else -request.quantity)
        if self.config.risk.long_only and future_qty < 0:
            return RiskDecision(False, reason="long_only restriction")
        if self.config.risk.short_only and future_qty > 0:
            return RiskDecision(False, reason="short_only restriction")
        price = market_state.mid if request.price is None else request.price
        notional = abs(request.quantity * price)
        if notional > self.config.risk.max_order_notional:
            return RiskDecision(False, reason="order notional exceeds limit")
        per_symbol = self.config.risk.per_symbol_notional.get(symbol)
        if per_symbol and abs(future_qty * price) > per_symbol:
            return RiskDecision(False, reason="per-symbol notional limit")
        total_exposure = 0.0
        for pos in positions.values():
            ref_price = market_state.mid if pos.symbol == symbol else pos.entry_price
            total_exposure += abs(pos.quantity * ref_price)
        projected_exposure = total_exposure + notional
        leverage = projected_exposure / max(account.equity, 1e-9)
        if leverage > self.config.risk.max_leverage:
            return RiskDecision(False, reason="leverage limit breached")
        if len([pos for pos in positions.values() if abs(pos.quantity) > 0.0]) >= self.config.risk.max_open_positions:
            if symbol not in positions or abs(positions[symbol].quantity) < 1e-9:
                return RiskDecision(False, reason="max open positions reached")
        spread_bps = market_state.spread / max(market_state.mid, 1e-9) * 10_000
        if spread_bps > self.max_spread_bps:
            return RiskDecision(False, reason="spread too wide")
        return RiskDecision(True)

    def on_market(self, state: MarketState) -> None:
        self.last_market_time = state.time

    def on_fill(self, symbol: str, quantity: float, price: float, account: AccountState) -> None:
        position = self.positions.get(symbol, Position(symbol=symbol, quantity=0.0, entry_price=0.0))
        new_qty = position.quantity + quantity
        if abs(new_qty) < 1e-9:
            self.positions[symbol] = Position(symbol=symbol, quantity=0.0, entry_price=0.0)
        else:
            avg_price = (
                (position.entry_price * position.quantity + price * quantity) / new_qty
                if position.quantity != 0
                else price
            )
            self.positions[symbol] = Position(symbol=symbol, quantity=new_qty, entry_price=avg_price)
        self._update_equity(account.equity)

    def on_pnl_update(self, equity: float) -> None:
        self._update_equity(equity)

    def register_adapter_error(self) -> None:
        self.adapter_errors += 1

    # ------------------------------------------------------------------
    def _update_equity(self, equity: float) -> None:
        today = date.today()
        if self.state.day != today:
            self.state = RiskState(start_equity=equity, peak_equity=equity, day=today)
            return
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        drawdown = 0.0
        if self.state.peak_equity > 0:
            drawdown = 1 - equity / self.state.peak_equity
        daily_loss = 0.0
        if self.state.start_equity > 0:
            daily_loss = 1 - equity / self.state.start_equity
        if daily_loss >= self.config.risk.max_daily_loss:
            self.state.kill_triggered = True
            self.state.kill_reason = "daily loss limit"
        if drawdown >= self.config.risk.max_drawdown:
            self.state.kill_triggered = True
            self.state.kill_reason = "drawdown limit"


__all__ = ["RiskManager", "RiskDecision"]
