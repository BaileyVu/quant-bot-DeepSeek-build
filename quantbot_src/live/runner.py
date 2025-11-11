"""Live and paper trading runner."""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Optional

from contextlib import suppress

from ..config import Settings, get_settings
from ..data.normalizer import MarketNormalizer
from ..logging_setup import configure_logging, log_extra
from ..risk.limits import LimitChecker
from ..risk.stops import StopManager
from ..strategy.momentum import MomentumStrategy
from ..utils.time import utc_now
from ..backtest.datasets import synthetic_dataset
from ..exec.broker import PaperBroker
from ..exec.positions import PositionTracker
from ..exec.router import Router
from .heartbeat import Heartbeat

logger = logging.getLogger(__name__)


async def paper_loop(settings: Settings) -> None:
    dataset = synthetic_dataset(settings.symbol, settings.bar_interval, periods=60)
    broker = PaperBroker(settings.maker_fee_bps / 10_000, settings.taker_fee_bps / 10_000)
    router = Router(broker)
    tracker = PositionTracker()
    normalizer = MarketNormalizer()
    strategy = MomentumStrategy()
    limit_checker = LimitChecker()
    stop_manager = StopManager(10_000.0)
    heartbeat = Heartbeat()

    async def stale_callback() -> None:
        logger.warning("stale book detected - pausing trading")

    watchdog = asyncio.create_task(heartbeat.watch(stale_callback))

    cash = 10_000.0
    try:
        for bar in dataset.bars:
            state = normalizer.update_from_bar(bar)
            heartbeat.beat()
            equity = cash + tracker.position.qty * state.mid
            if not stop_manager.check_daily(equity):
                logger.error("kill switch triggered")
                break
            target = strategy.on_bar(state)
            notional = target.qty * state.mid
            if not limit_checker.check_leverage(notional).allowed:
                continue
            current_qty = tracker.position.qty
            result = await router.route_to_target(settings.symbol, current_qty, target.qty, state)
            if result:
                fill_qty = result.fill["qty"]
                fill_price = result.fill["price"]
                tracker.update(settings.symbol, fill_qty, fill_price)
                cash -= fill_qty * fill_price
            equity = cash + tracker.position.qty * state.mid
            logger.info("heartbeat", extra=log_extra(equity=equity, position=tracker.position.qty))
            await asyncio.sleep(0.05)
    finally:
        watchdog.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog


def main(args: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="quantbot live runner")
    parser.add_argument("--mode", default="paper")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default=None)
    parsed = parser.parse_args(args)
    settings = get_settings().model_copy()
    updates = {"mode": parsed.mode, "exchange": parsed.exchange}
    if parsed.symbol:
        updates["symbol"] = parsed.symbol
    settings = settings.model_copy(update=updates)
    configure_logging()
    logger.info("starting runner", extra={"_json_extras_run": {"mode": settings.mode, "exchange": settings.exchange}})
    if settings.mode == "paper":
        asyncio.run(paper_loop(settings))
    else:
        logger.error("live mode not implemented in offline environment")


if __name__ == "__main__":
    main()
