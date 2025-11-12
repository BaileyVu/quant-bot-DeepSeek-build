"""Event-driven backtest engine with risk integration."""
from __future__ import annotations

import argparse
import gzip
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping

from ..config import Settings, get_settings, load_settings
from ..data.events import FillEvent, MarketEvent, OrderEvent, RiskEvent, SignalEvent
from ..data.normalizer import MarketNormalizer
from ..exchange.models import AccountState, OrderRequest, Position, SymbolMeta
from ..logging_setup import configure_logging
from ..risk.manager import RiskDecision, RiskManager
from ..risk.funding import FundingModel
from ..strategy.base import Strategy
from ..strategy.momentum import MomentumStrategy
from ..storage.db import init_db, record_metric
from ..telemetry.metrics import metrics
from ..utils.time import to_unix_ms, utc_now
from .datasets import HistoricalData, synthetic_dataset
from .metrics import EquityPoint, compute_metrics


logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    equity_curve: List[EquityPoint]
    metrics: Mapping[str, float]
    replay_path: Path | None = None


class ReplayLogger:
    """Persist events to gzipped JSONL for replay."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "events.jsonl.gz"
        self._file = gzip.open(self.path, "wt", encoding="utf-8")

    def log(self, payload: dict) -> None:
        self._file.write(json.dumps(payload, separators=(",", ":")))
        self._file.write("\n")

    def close(self) -> None:
        self._file.close()


class BacktestEngine:
    def __init__(
        self,
        settings: Settings,
        strategy: Strategy,
        data: HistoricalData,
        starting_equity: float = 10_000.0,
        enable_replay: bool = True,
    ) -> None:
        self.settings = settings
        self.strategy = strategy
        self.data = data
        self.normalizer = MarketNormalizer()
        self.funding_model = FundingModel(settings.execution.funding_interval_minutes)
        self.starting_equity = starting_equity
        self.position_qty = 0.0
        self.cash = starting_equity
        self.avg_price = 0.0
        self._last_mid = 0.0
        self.symbol = settings.symbol
        self.symbol_meta = SymbolMeta(
            symbol=self.symbol,
            price_precision=2,
            size_precision=3,
            tick_size=0.1,
            step_size=0.001,
            min_notional=5.0,
            max_leverage=settings.risk.max_leverage,
        )
        self.risk_manager = RiskManager(settings)
        run_id = utc_now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = Path("runs") / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.replay = ReplayLogger(self.run_dir) if enable_replay else None

    def _account_state(self, timestamp) -> AccountState:
        equity = self.cash + self.position_qty * self._last_mid
        return AccountState(
            equity=equity,
            available_balance=self.cash,
            timestamp=timestamp,
            margin_ratio=None,
        )

    def _positions(self) -> Mapping[str, Position]:
        if abs(self.position_qty) < 1e-9:
            return {}
        return {
            self.symbol: Position(
                symbol=self.symbol,
                qty=self.position_qty,
                entry_price=self.avg_price,
            )
        }

    def _log_event(self, payload: dict) -> None:
        if self.replay:
            self.replay.log(payload)

    def _record_market_event(self, event: MarketEvent) -> None:
        self._log_event({
            "type": "market",
            "symbol": event.symbol,
            "timestamp": event.timestamp.isoformat(),
            "mid": event.state.mid,
            "spread": event.state.spread,
        })

    def _record_signal_event(self, event: SignalEvent) -> None:
        self._log_event({
            "type": "signal",
            "symbol": event.symbol,
            "timestamp": event.timestamp.isoformat(),
            "target_qty": event.target_qty,
            "confidence": event.confidence,
        })

    def _record_order_event(self, event: OrderEvent, decision: RiskDecision) -> None:
        payload = {
            "type": "order",
            "symbol": event.symbol,
            "timestamp": event.timestamp.isoformat(),
            "side": event.side,
            "qty": event.qty,
            "price": event.price,
            "decision": decision.allowed,
            "reason": decision.reason,
        }
        if decision.metadata:
            payload["meta"] = decision.metadata
        self._log_event(payload)

    def _record_fill_event(self, event: FillEvent) -> None:
        self._log_event({
            "type": "fill",
            "symbol": event.symbol,
            "timestamp": event.timestamp.isoformat(),
            "qty": event.qty,
            "price": event.price,
            "fee": event.fee,
        })

    def _record_risk_event(self, event: RiskEvent) -> None:
        self._log_event({
            "type": "risk",
            "symbol": event.symbol,
            "timestamp": event.timestamp.isoformat(),
            "allowed": event.allowed,
            "reason": event.reason,
        })

    def _slippage(self, spread: float, delta_qty: float) -> float:
        impact = spread * 0.1 + abs(delta_qty) * 0.5
        direction = 1 if delta_qty > 0 else -1
        return direction * impact

    def run(self) -> BacktestResult:
        init_db()
        equity_curve: list[EquityPoint] = []
        for bar in self.data.bars:
            state = self.normalizer.update_from_bar(bar)
            self._last_mid = state.mid
            market_event = MarketEvent(symbol=self.symbol, timestamp=bar.open_time, state=state)
            self._record_market_event(market_event)
            account_state = self._account_state(bar.open_time)
            self.risk_manager.register_market_state(self.symbol, state)
            self.risk_manager.on_pnl_update(account_state.equity, bar.open_time)

            target = self.strategy.on_bar(state)
            signal_event = SignalEvent(
                strategy_id=self.strategy.__class__.__name__,
                symbol=self.symbol,
                timestamp=bar.open_time,
                target_qty=target.qty,
            )
            self._record_signal_event(signal_event)
            delta = target.qty - self.position_qty
            if abs(delta) < 1e-8:
                equity_curve.append(EquityPoint(timestamp=to_unix_ms(bar.open_time), equity=account_state.equity))
                continue
            side = "buy" if delta > 0 else "sell"
            order_request = OrderRequest(
                symbol=self.symbol,
                side=side,
                type="market",
                qty=abs(delta),
                price=None,
            )
            decision = self.risk_manager.validate_order(
                order_request,
                account_state,
                self._positions(),
                state,
                self.symbol_meta,
            )
            order_event = OrderEvent(
                symbol=self.symbol,
                timestamp=bar.open_time,
                side=side,
                qty=decision.order.qty if decision.order else abs(delta),
                price=decision.order.price if decision.order else None,
                order_type="market",
                client_order_id=f"bt-{len(equity_curve)}",
            )
            self._record_order_event(order_event, decision)
            if not decision.allowed or not decision.order:
                metrics.increment("orders_rejected")
                if decision.reason:
                    self._record_risk_event(
                        RiskEvent(
                            symbol=self.symbol,
                            timestamp=bar.open_time,
                            allowed=False,
                            reason=decision.reason,
                        )
                    )
                equity_curve.append(EquityPoint(timestamp=to_unix_ms(bar.open_time), equity=account_state.equity))
                continue
            metrics.increment("orders_submitted")

            sanitized = decision.order
            executed_qty = sanitized.qty if side == "buy" else -sanitized.qty
            effective_qty = executed_qty
            reference_price = sanitized.price or state.mid
            fill_price = reference_price + self._slippage(state.spread, effective_qty)
            notional_trade = effective_qty * fill_price
            fee_rate = self.settings.execution.taker_fee_bps / 10_000
            fee = abs(notional_trade) * fee_rate
            self.cash -= notional_trade + fee
            if self.position_qty + effective_qty != 0:
                self.avg_price = (
                    self.avg_price * self.position_qty + fill_price * effective_qty
                ) / (self.position_qty + effective_qty)
            else:
                self.avg_price = 0.0
            self.position_qty += effective_qty
            self.risk_manager.on_fill(self.symbol, effective_qty)
            metrics.increment("orders_filled")
            fill_event = FillEvent(
                symbol=self.symbol,
                timestamp=bar.open_time,
                order_id=order_event.client_order_id,
                client_order_id=order_event.client_order_id,
                qty=effective_qty,
                price=fill_price,
                fee=fee,
            )
            self._record_fill_event(fill_event)
            funding = 0.0
            if self.funding_model.should_apply(bar.open_time):
                funding = self.funding_model.apply(bar.open_time, self.position_qty * state.mid, 0.0001)
                self.cash += funding
            equity = self.cash + self.position_qty * state.mid
            metrics.set_gauge("equity", equity)
            metrics.set_gauge("position_qty", self.position_qty)
            metrics.set_gauge("cash_balance", self.cash)
            equity_curve.append(EquityPoint(timestamp=to_unix_ms(bar.open_time), equity=equity))

        summary = compute_metrics(equity_curve)
        record_metric(self.run_dir.name, summary)
        if self.replay:
            self.replay.close()
        return BacktestResult(
            equity_curve=equity_curve,
            metrics=summary,
            replay_path=self.replay.path if self.replay else None,
        )


def run_cli(args: list[str] | None = None) -> BacktestResult:
    parser = argparse.ArgumentParser(description="quantbot backtest runner")
    parser.add_argument("--config", type=Path, default=None, help="Path to config TOML file")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--bars", type=int, default=500)
    parsed = parser.parse_args(args=args)

    if parsed.config:
        settings = load_settings(parsed.config, use_cache=False)
    else:
        settings = get_settings()
    if parsed.symbol:
        runtime = settings.runtime.model_copy(update={"symbols": [parsed.symbol]})
        settings = settings.model_copy(update={"runtime": runtime})

    run_id = configure_logging()
    logger.info(
        "backtest_start",
        extra={
            "_json_extras_log": {
                "run_id": run_id,
                "mode": settings.mode,
                "exchange": settings.exchange,
                "symbols": settings.symbols,
                "config": str(parsed.config) if parsed.config else "env",
            }
        },
    )

    data = synthetic_dataset(settings.symbol, settings.runtime.bar_interval, parsed.bars)
    strategy = MomentumStrategy()
    engine = BacktestEngine(settings=settings, strategy=strategy, data=data)
    result = engine.run()
    print(json.dumps(result.metrics, indent=2))
    return result


if __name__ == "__main__":
    run_cli()
