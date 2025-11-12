"""Live and paper trading runner."""
from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import Optional

from ..backtest.datasets import synthetic_dataset
from ..config import Settings, get_settings, load_settings
from ..data.normalizer import MarketNormalizer
from ..exchange import BinanceFuturesAdapter, HyperliquidAdapter, OrderRequest
from ..logging_setup import configure_logging, log_extra
from ..risk.manager import RiskManager
from ..strategy.momentum import MomentumStrategy
from ..telemetry.metrics import metrics
from .heartbeat import Heartbeat

logger = logging.getLogger(__name__)


def build_adapter(settings: Settings):
    if settings.exchange == "binance":
        return BinanceFuturesAdapter(settings)
    return HyperliquidAdapter(settings)


async def paper_loop(settings: Settings, periods: int = 120) -> None:
    dataset = synthetic_dataset(settings.symbol, settings.runtime.bar_interval, periods=periods)
    adapter = build_adapter(settings)
    normalizer = MarketNormalizer()
    strategy = MomentumStrategy()
    risk_manager = RiskManager(settings)
    heartbeat = Heartbeat()

    async def stale_callback() -> None:
        logger.warning("stale book detected - pausing trading")

    watchdog = asyncio.create_task(heartbeat.watch(stale_callback))

    try:
        for bar in dataset.bars:
            state = normalizer.update_from_bar(bar)
            heartbeat.beat()
            account = await adapter.get_account()
            positions = await adapter.get_positions()
            risk_manager.register_market_state(settings.symbol, state)
            risk_manager.on_pnl_update(account.equity, bar.open_time)
            target = strategy.on_bar(state)
            current_qty = positions.get(settings.symbol).qty if settings.symbol in positions else 0.0
            delta = target.qty - current_qty
            if abs(delta) < 1e-8:
                logger.info("no_change", extra=log_extra(position=current_qty, equity=account.equity))
                await asyncio.sleep(0.05)
                continue
            side = "buy" if delta > 0 else "sell"
            symbol_meta = await adapter.get_symbol_meta(settings.symbol)
            order_request = OrderRequest(
                symbol=settings.symbol,
                side=side,
                type="market",
                qty=abs(delta),
                price=None,
            )
            decision = risk_manager.validate_order(
                order_request,
                account,
                positions,
                state,
                symbol_meta,
            )
            if not decision.allowed or not decision.order:
                metrics.increment("orders_rejected")
                logger.warning(
                    "order_blocked",
                    extra=log_extra(reason=decision.reason, position=current_qty, target=target.qty),
                )
                await asyncio.sleep(0.1)
                continue
            metrics.increment("orders_submitted")
            placed = await adapter.place_order(decision.order)
            signed_qty = decision.order.qty if decision.order.side == "buy" else -decision.order.qty
            risk_manager.on_fill(settings.symbol, signed_qty)
            metrics.increment("orders_filled")
            metrics.set_gauge("position_qty", signed_qty + current_qty)
            logger.info(
                "order_filled",
                extra=log_extra(
                    order_id=placed.order_id,
                    qty=signed_qty,
                    price=placed.price,
                    fee=placed.meta.get("fee", 0.0),
                    equity=account.equity,
                ),
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
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--config", type=Path, default=None)
    parsed = parser.parse_args(args)

    settings = load_settings(parsed.config) if parsed.config else get_settings()
    runtime_updates = {}
    if parsed.exchange:
        runtime_updates["exchange"] = parsed.exchange
    if parsed.symbol:
        runtime_updates["symbols"] = [parsed.symbol]
    if runtime_updates:
        runtime = settings.runtime.model_copy(update=runtime_updates)
        settings = settings.model_copy(update={"runtime": runtime})

    run_id = configure_logging()
    logger.info(
        "starting runner",
        extra=log_extra(run_id=run_id, mode=settings.mode, exchange=settings.exchange, symbols=settings.symbols),
    )
    if settings.mode == "paper":
        asyncio.run(paper_loop(settings))
    else:
        logger.error("live mode not implemented in offline environment")


if __name__ == "__main__":
    main()
