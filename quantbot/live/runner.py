"""Live and paper trading runner."""
from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import suppress
from typing import Optional

from ..config import get_config
from ..core import OrderRequest
from ..data import MarketNormalizer
from ..exchange import AccountState, Position
from ..logging_setup import configure_logging, log_extra
from ..risk import RiskManager
from ..strategy.momentum import MomentumStrategy
from ..utils.time import utc_now
from ..backtest.datasets import synthetic_dataset
from ..exec.broker import PaperBroker
from ..exec.positions import PositionTracker
from ..exec.router import Router
from .heartbeat import Heartbeat

logger = logging.getLogger(__name__)


async def paper_loop() -> None:
    cfg = configure_logging()
    dataset = synthetic_dataset(cfg.runtime.primary_symbol, cfg.runtime.bar_interval, periods=600)
    broker = PaperBroker(cfg.fees.maker_rate, cfg.fees.taker_rate)
    router = Router(broker)
    tracker = PositionTracker()
    normalizer = MarketNormalizer()
    strategy = MomentumStrategy()
    risk_manager = RiskManager(cfg)
    heartbeat = Heartbeat()

    async def stale_callback() -> None:
        logger.warning("stale book detected - pausing trading")
        risk_manager.state.kill_triggered = True
        risk_manager.state.kill_reason = "data stale"

    watchdog = asyncio.create_task(heartbeat.watch(stale_callback))

    cash = 100_000.0
    try:
        for bar in dataset.bars:
            state = normalizer.update_from_bar(bar)
            heartbeat.beat()
            risk_manager.on_market(state)
            account_state = AccountState(
                equity=cash + tracker.position.qty * state.mid,
                available_margin=cash,
                total_margin=cash + tracker.position.qty * state.mid,
                timestamp=state.time,
            )
            if not risk_manager.is_trading_allowed():
                logger.error("kill switch triggered", extra=log_extra(reason=risk_manager.state.kill_reason))
                break
            target = strategy.on_bar(state)
            current_qty = tracker.position.qty if tracker.position.symbol == cfg.runtime.primary_symbol else 0.0
            delta = target.qty - current_qty
            if abs(delta) < 1e-8:
                continue
            side = "buy" if delta > 0 else "sell"
            request = OrderRequest(
                symbol=cfg.runtime.primary_symbol,
                side=side,
                quantity=abs(delta),
                order_type="limit",
                price=state.mid,
            )
            positions = {}
            if tracker.position.symbol:
                positions[tracker.position.symbol] = Position(
                    symbol=tracker.position.symbol,
                    quantity=tracker.position.qty,
                    entry_price=tracker.position.avg_price,
                )
            decision = risk_manager.validate_order(request, state, account_state, positions)
            if not decision.allowed:
                logger.info("risk rejected order", extra=log_extra(reason=decision.reason))
                continue
            request = decision.adjusted_order or request
            result = await router.route_to_target(
                cfg.runtime.primary_symbol,
                current_qty,
                current_qty + (request.quantity if request.side == "buy" else -request.quantity),
                state,
            )
            if result:
                fill_qty = result.fill["qty"] if result.fill else request.quantity
                fill_price = result.fill.get("price", state.mid)
                fill_signed = fill_qty if request.side == "buy" else -fill_qty
                tracker.update(cfg.runtime.primary_symbol, fill_signed, fill_price)
                cash -= fill_signed * fill_price
                account_state.equity = cash + tracker.position.qty * state.mid
                account_state.available_margin = cash
                account_state.total_margin = account_state.equity
                risk_manager.on_fill(cfg.runtime.primary_symbol, fill_signed, fill_price, account_state)
            equity = cash + tracker.position.qty * state.mid
            risk_manager.on_pnl_update(equity)
            logger.info(
                "heartbeat",
                extra=log_extra(equity=equity, position=tracker.position.qty, price=state.mid),
            )
            await asyncio.sleep(0.05)
    finally:
        watchdog.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog


def main(args: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="quantbot live runner")
    parser.add_argument("--mode", default="paper")
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--symbol", default=None)
    parsed = parser.parse_args(args)
    overrides: dict[str, dict] = {}
    if parsed.exchange:
        overrides.setdefault("runtime", {})["exchange"] = parsed.exchange
    if parsed.symbol:
        overrides.setdefault("runtime", {})["primary_symbol"] = parsed.symbol
    get_config(force_reload=True, config_path=parsed.config, overrides=overrides or None)
    if parsed.mode == "paper":
        asyncio.run(paper_loop())
    else:
        logger.error("live mode not implemented in offline environment")


if __name__ == "__main__":
    main()
