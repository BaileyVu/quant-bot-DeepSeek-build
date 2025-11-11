"""Event-driven backtest engine."""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from ..config import Settings, get_settings
from ..data.normalizer import MarketNormalizer, MarketState
from ..risk.funding import FundingModel
from ..risk.limits import LimitChecker
from ..risk.stops import StopManager
from ..strategy.base import Strategy
from ..strategy.momentum import MomentumStrategy
from ..storage.db import init_db, record_metric
from ..utils.time import to_unix_ms, utc_now
from .datasets import HistoricalData, synthetic_dataset
from .metrics import EquityPoint, compute_metrics


@dataclass
class BacktestResult:
    equity_curve: List[EquityPoint]
    metrics: dict


class BacktestEngine:
    def __init__(
        self,
        settings: Settings,
        strategy: Strategy,
        data: HistoricalData,
        starting_equity: float = 10_000.0,
    ) -> None:
        self.settings = settings
        self.strategy = strategy
        self.data = data
        self.normalizer = MarketNormalizer()
        self.limit_checker = LimitChecker(equity=starting_equity)
        self.stop_manager = StopManager(starting_equity)
        self.funding_model = FundingModel(settings.funding_interval_minutes)
        self.starting_equity = starting_equity
        self.position_qty = 0.0
        self.cash = starting_equity
        self.avg_price = 0.0
        random.seed(1337)

    def _slippage(self, state: MarketState, delta_qty: float) -> float:
        impact = state.spread * 0.1 + state.realized_vol * abs(delta_qty)
        direction = 1 if delta_qty > 0 else -1
        return direction * impact

    def _fee(self, notional: float) -> float:
        fee_rate = self.settings.taker_fee_bps / 10_000
        return abs(notional) * fee_rate

    def run(self) -> BacktestResult:
        init_db()
        equity_curve: List[EquityPoint] = []
        for bar in self.data.bars:
            state = self.normalizer.update_from_bar(bar)
            if not self.stop_manager.check_daily(self.cash + self._position_value(state)):
                break
            target = self.strategy.on_bar(state)
            notional = target.qty * state.mid
            limit_check = self.limit_checker.check_leverage(notional)
            if not limit_check.allowed:
                continue
            delta = target.qty - self.position_qty
            if abs(delta) > 1e-8:
                fill_price = state.mid + self._slippage(state, delta)
                notional_trade = delta * fill_price
                fee = self._fee(notional_trade)
                self.cash -= notional_trade + fee
                if self.position_qty + delta != 0:
                    self.avg_price = (
                        self.avg_price * self.position_qty + fill_price * delta
                    ) / (self.position_qty + delta)
                else:
                    self.avg_price = 0.0
                self.position_qty += delta
            funding_rate = 0.0
            if self.funding_model.should_apply(state.time):
                funding_rate = 0.0001
                payment = self.funding_model.apply(state.time, self.position_qty * state.mid, funding_rate)
                self.cash += payment
            equity = self.cash + self._position_value(state)
            equity_curve.append(EquityPoint(timestamp=to_unix_ms(state.time), equity=equity))
        metrics = compute_metrics(equity_curve)
        run_id = utc_now().strftime("%Y%m%d-%H%M%S")
        self._write_equity(run_id, equity_curve)
        record_metric(run_id, metrics)
        return BacktestResult(equity_curve=equity_curve, metrics=metrics)

    def _position_value(self, state: MarketState) -> float:
        return self.position_qty * state.mid

    def _write_equity(self, run_id: str, equity_curve: List[EquityPoint]) -> None:
        runs_dir = Path("runs")
        runs_dir.mkdir(exist_ok=True)
        run_dir = runs_dir / run_id
        run_dir.mkdir(exist_ok=True)
        path = run_dir / "equity.csv"
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "equity"])
            for point in equity_curve:
                writer.writerow([point.timestamp, point.equity])


def run_cli(args: list[str] | None = None) -> BacktestResult:
    parser = argparse.ArgumentParser(description="quantbot backtest runner")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--bars", type=int, default=500)
    parsed = parser.parse_args(args=args)
    settings = get_settings().model_copy()
    settings = settings.model_copy(update={"symbol": parsed.symbol})
    data = synthetic_dataset(settings.symbol, settings.bar_interval, parsed.bars)
    strategy = MomentumStrategy()
    init_db()
    engine = BacktestEngine(settings=settings, strategy=strategy, data=data)
    result = engine.run()
    print(json.dumps(result.metrics, indent=2))
    return result


if __name__ == "__main__":
    run_cli()
