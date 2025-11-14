"""Run a grid of backtest scenarios in parallel."""
from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

import pandas as pd

from quantbot.backtest.datasets import synthetic_dataset
from quantbot.backtest.engine import BacktestEngine
from quantbot.config import get_config
from quantbot.strategy.momentum import MomentumConfig, MomentumStrategy


def parse_grid(values: str, *, cast=float) -> Sequence[float]:
    tokens = [token.strip() for token in values.split(",") if token.strip()]
    return [cast(token) for token in tokens]


def run_scenario(config_path: str | None, fast: int, slow: int, z_clip: float, bars: int) -> dict:
    overrides = {"runtime": {"mode": "backtest"}}
    cfg = get_config(force_reload=True, config_path=config_path, overrides=overrides)
    data = synthetic_dataset(cfg.runtime.primary_symbol, cfg.runtime.bar_interval, periods=bars)
    strategy = MomentumStrategy(MomentumConfig(fast=fast, slow=slow, z_clip=z_clip))
    engine = BacktestEngine(config=cfg, strategy=strategy, data=data)
    result = engine.run()
    return {
        "fast": fast,
        "slow": slow,
        "z_clip": z_clip,
        "final_equity": result.equity_curve[-1].equity if result.equity_curve else 0.0,
        "sharpe": result.metrics.get("sharpe", 0.0),
        "max_drawdown": result.metrics.get("max_drawdown", 0.0),
        "hit_rate": result.metrics.get("hit_rate", 0.0),
        "run_id": result.run_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel backtest sweep")
    parser.add_argument("--config", default="configs/binance_backtest.toml")
    parser.add_argument("--fast", default="10,20,30")
    parser.add_argument("--slow", default="50,75,100")
    parser.add_argument("--z-clip", default="1.5,2.0,2.5")
    parser.add_argument("--bars", type=int, default=2000)
    parser.add_argument("--output", default="results/backtest_grid.csv")
    args = parser.parse_args()

    fast_values = parse_grid(args.fast, cast=int)
    slow_values = parse_grid(args.slow, cast=int)
    z_values = parse_grid(args.z_clip, cast=float)
    scenarios = list(itertools.product(fast_values, slow_values, z_values))

    results_dir = Path(args.output).resolve().parent
    results_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    with ProcessPoolExecutor() as executor:
        futures = [
            executor.submit(run_scenario, args.config, fast, slow, z_clip, args.bars)
            for fast, slow, z_clip in scenarios
        ]
        for future in as_completed(futures):
            rows.append(future.result())

    df = pd.DataFrame(rows)
    df.sort_values(by="sharpe", ascending=False, inplace=True)
    df.to_csv(args.output, index=False)
    print(json.dumps({"output": args.output, "rows": len(df)}, indent=2))


if __name__ == "__main__":
    main()
