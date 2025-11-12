"""Event-driven backtest engine."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import timedelta
from pathlib import Path
from typing import List

from ..config import AppConfig, get_config
from ..core import MarketEvent, OrderRequest, ReplayEvent, SignalEvent
from ..data import MarketNormalizer, MarketState
from ..exchange import AccountState, Position
from ..logging_setup import configure_logging
from ..risk import RiskManager
from ..risk.funding import FundingModel
from ..storage.db import init_db, record_metric
from ..strategy.base import Strategy, Target
from ..strategy.momentum import MomentumStrategy
from ..utils.time import to_unix_ms, utc_now
from .datasets import HistoricalData, synthetic_dataset
from .metrics import EquityPoint, compute_metrics


@dataclass
class BacktestResult:
    equity_curve: List[EquityPoint]
    metrics: dict
    run_id: str


class BacktestEngine:
    def __init__(
        self,
        config: AppConfig,
        strategy: Strategy,
        data: HistoricalData,
        *,
        starting_equity: float = 100_000.0,
        risk_manager: RiskManager | None = None,
        events_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.strategy = strategy
        self.data = data
        self.normalizer = MarketNormalizer()
        self.risk_manager = risk_manager or RiskManager(config, max_data_lag=timedelta.max)
        self.funding_model = FundingModel(config.runtime.funding_interval_minutes)
        self.starting_equity = starting_equity
        self.cash = starting_equity
        self.positions: dict[str, Position] = {
            symbol: Position(symbol=symbol, quantity=0.0, entry_price=0.0)
            for symbol in config.runtime.symbols
        }
        self.last_prices: dict[str, float] = {symbol: 0.0 for symbol in config.runtime.symbols}
        self.equity_curve: list[EquityPoint] = []
        self.events_dir = events_dir or Path("runs")
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self._event_file = None
        self._record_path: Path | None = None

    # ------------------------------------------------------------------
    def run(self) -> BacktestResult:
        init_db()
        run_id = self._prepare_run_directory()
        account_state = AccountState(
            equity=self.starting_equity,
            available_margin=self.starting_equity,
            total_margin=self.starting_equity,
            timestamp=utc_now(),
        )
        for sequence, bar in enumerate(self.data.bars):
            state = self.normalizer.update_from_bar(bar)
            self.last_prices[bar.symbol] = state.mid
            self.risk_manager.on_market(state)
            self._record_event(
                "market",
                MarketEvent(symbol=bar.symbol, state=state, timestamp=state.time, bar=bar, sequence=sequence),
            )
            account_state = self._account_state(state)
            if not self.risk_manager.is_trading_allowed():
                self._record_event(
                    "risk_halt",
                    {"reason": self.risk_manager.state.kill_reason, "equity": account_state.equity},
                )
                break
            target = self.strategy.on_bar(state)
            self._record_event(
                "signal",
                SignalEvent(
                    strategy_id=self.strategy.__class__.__name__,
                    symbol=bar.symbol,
                    target_qty=target.qty,
                    timestamp=state.time,
                ),
            )
            self._trade_to_target(bar.symbol, state, target, account_state)
            self._apply_funding(state)
            equity = self._mark_to_market()
            self.risk_manager.on_pnl_update(equity)
            self.equity_curve.append(EquityPoint(timestamp=to_unix_ms(state.time), equity=equity))
        metrics = compute_metrics(self.equity_curve)
        record_metric(run_id, metrics)
        self._close_event_file()
        return BacktestResult(equity_curve=self.equity_curve, metrics=metrics, run_id=run_id)

    # ------------------------------------------------------------------
    def _trade_to_target(
        self,
        symbol: str,
        state: MarketState,
        target: Target,
        account_state: AccountState,
    ) -> None:
        position = self.positions.get(symbol)
        current_qty = position.quantity if position else 0.0
        delta = target.qty - current_qty
        if abs(delta) < 1e-8:
            return
        side = "buy" if delta > 0 else "sell"
        request = OrderRequest(
            symbol=symbol,
            side=side,
            quantity=abs(delta),
            order_type="market",
            price=state.mid,
        )
        decision = self.risk_manager.validate_order(
            request,
            state,
            account_state,
            positions=self.positions,
        )
        if not decision.allowed:
            self._record_event("risk_reject", {"symbol": symbol, "reason": decision.reason})
            return
        request = decision.adjusted_order or request
        fill_qty = request.quantity if request.side == "buy" else -request.quantity
        fill_price = state.mid + self._slippage(state, fill_qty)
        fee = abs(fill_qty * fill_price) * self.config.fees.taker_rate
        self.cash -= fill_qty * fill_price + fee
        new_position = self._update_position(symbol, fill_qty, fill_price)
        account_state.equity = self._mark_to_market()
        account_state.available_margin = self.cash
        account_state.total_margin = account_state.equity
        account_state.timestamp = state.time
        self.risk_manager.on_fill(symbol, fill_qty, fill_price, account_state)
        self._record_event(
            "fill",
            {
                "symbol": symbol,
                "side": request.side,
                "qty": fill_qty,
                "price": fill_price,
                "fee": fee,
                "position": new_position.quantity,
            },
        )

    def _update_position(self, symbol: str, qty_delta: float, price: float) -> Position:
        position = self.positions.get(symbol, Position(symbol=symbol, quantity=0.0, entry_price=0.0))
        new_qty = position.quantity + qty_delta
        if abs(new_qty) < 1e-9:
            updated = Position(symbol=symbol, quantity=0.0, entry_price=0.0)
        else:
            if abs(position.quantity) < 1e-9:
                avg_price = price
            else:
                avg_price = (position.entry_price * position.quantity + price * qty_delta) / new_qty
            updated = Position(symbol=symbol, quantity=new_qty, entry_price=avg_price)
        self.positions[symbol] = updated
        return updated

    def _mark_to_market(self) -> float:
        equity = self.cash
        for symbol, position in self.positions.items():
            price = self.last_prices.get(symbol, position.entry_price)
            equity += position.quantity * price
        return equity

    def _apply_funding(self, state: MarketState) -> None:
        position = self.positions.get(state.symbol)
        if not position or abs(position.quantity) < 1e-9:
            return
        if not self.funding_model.should_apply(state.time):
            return
        payment = self.funding_model.apply(state.time, position.quantity * state.mid, 0.0001)
        if abs(payment) < 1e-12:
            return
        self.cash += payment
        self._record_event("funding", {"symbol": state.symbol, "payment": payment})

    def _account_state(self, state) -> AccountState:
        equity = self._mark_to_market()
        return AccountState(
            equity=equity,
            available_margin=self.cash,
            total_margin=equity,
            timestamp=state.time,
        )

    def _slippage(self, state, delta_qty: float) -> float:
        impact = state.spread * 0.1 + state.realized_vol * abs(delta_qty)
        direction = 1 if delta_qty > 0 else -1
        return direction * impact

    def _prepare_run_directory(self) -> str:
        run_id = utc_now().strftime("%Y%m%d-%H%M%S")
        run_dir = self.events_dir / run_id
        run_dir.mkdir(exist_ok=True)
        self._record_path = run_dir / "events.jsonl"
        self._event_file = self._record_path.open("w", encoding="utf-8")
        return run_id

    def _record_event(self, event_type: str, payload) -> None:
        if self._event_file is None:
            return
        if isinstance(payload, ReplayEvent):
            record = payload.to_json()
        else:
            serialized = self._serialize_payload(payload)
            record = {
                "type": event_type,
                "timestamp": serialized.pop("timestamp", utc_now().isoformat()),
                "payload": serialized,
            }
        self._event_file.write(json.dumps(record) + "\n")

    def _close_event_file(self) -> None:
        if self._event_file:
            self._event_file.close()
            self._event_file = None

    @staticmethod
    def _serialize_payload(payload) -> dict:
        if isinstance(payload, dict):
            data = payload
        elif is_dataclass(payload):
            data = asdict(payload)
        elif hasattr(payload, "__dict__"):
            data = dict(payload.__dict__)
        else:
            return {"value": payload, "timestamp": utc_now().isoformat()}
        normalized = BacktestEngine._normalize_structure(data)
        if "timestamp" not in normalized:
            normalized["timestamp"] = utc_now().isoformat()
        return normalized

    @staticmethod
    def _normalize_structure(value):
        if isinstance(value, dict):
            return {key: BacktestEngine._normalize_structure(val) for key, val in value.items()}
        if isinstance(value, list):
            return [BacktestEngine._normalize_structure(item) for item in value]
        if is_dataclass(value):
            return BacktestEngine._normalize_structure(asdict(value))
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value


def run_cli(args: list[str] | None = None) -> BacktestResult:
    parser = argparse.ArgumentParser(description="quantbot backtest runner")
    parser.add_argument("--config", default=None, help="Path to config TOML file")
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--mode", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--bars", type=int, default=500)
    parsed = parser.parse_args(args=args)
    overrides: dict[str, dict] = {}
    if parsed.exchange:
        overrides.setdefault("runtime", {})["exchange"] = parsed.exchange
    if parsed.mode:
        overrides.setdefault("runtime", {})["mode"] = parsed.mode
    if parsed.symbol:
        overrides.setdefault("runtime", {})["primary_symbol"] = parsed.symbol
    cfg = get_config(force_reload=True, config_path=parsed.config, overrides=overrides or None)
    configure_logging(cfg)
    data = synthetic_dataset(cfg.runtime.primary_symbol, cfg.runtime.bar_interval, periods=parsed.bars)
    strategy = MomentumStrategy()
    engine = BacktestEngine(config=cfg, strategy=strategy, data=data)
    result = engine.run()
    print(json.dumps(result.metrics, indent=2))
    return result


if __name__ == "__main__":
    run_cli()
