"""Run parameter sweeps for the momentum strategy in parallel."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Sequence

import sys
import os

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (SRC, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("ENVIRONMENT", "dev")

import pandas as pd

from quantbot.backtest.datasets import synthetic_dataset
from quantbot.backtest.engine import BacktestEngine
from quantbot.config import load_settings
from quantbot.strategy.momentum import MomentumConfig, MomentumStrategy


def build_param_grid(fast: Sequence[int], slow: Sequence[int], z_clip: Sequence[float]) -> list[dict[str, float | int]]:
    grid: list[dict[str, float | int]] = []
    for f in fast:
        for s in slow:
            if s <= f:
                continue
            for z in z_clip:
                grid.append({"fast": f, "slow": s, "z_clip": z})
    return grid


def run_single(config_path: Path, params: dict[str, float | int], bars: int) -> dict[str, float | int | float]:
    settings = load_settings(config_path, use_cache=False)
    data = synthetic_dataset(settings.symbol, settings.runtime.bar_interval, periods=bars)
    strategy = MomentumStrategy(
        MomentumConfig(
            fast=int(params["fast"]),
            slow=int(params["slow"]),
            z_clip=float(params["z_clip"]),
            max_leverage=settings.risk.max_leverage,
        )
    )
    engine = BacktestEngine(settings=settings, strategy=strategy, data=data, enable_replay=False)
    result = engine.run()
    output: dict[str, float | int | float] = {
        "fast": params["fast"],
        "slow": params["slow"],
        "z_clip": params["z_clip"],
    }
    output.update(result.metrics)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parallel backtests for parameter sweeps")
    parser.add_argument("--config", type=Path, default=Path("configs/binance_backtest.toml"))
    parser.add_argument("--bars", type=int, default=2000)
    parser.add_argument("--fast", nargs="*", type=int, default=[20, 50, 80])
    parser.add_argument("--slow", nargs="*", type=int, default=[100, 150, 200])
    parser.add_argument("--z", nargs="*", type=float, default=[1.0, 1.5, 2.0])
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--output", type=Path, default=Path("results/backtest_sweep.csv"))
    args = parser.parse_args()

    grid = build_param_grid(args.fast, args.slow, args.z)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, float | int | float]] = []
    with ProcessPoolExecutor(max_workers=args.processes) as pool:
        futures = [pool.submit(run_single, args.config, params, args.bars) for params in grid]
        for future in as_completed(futures):
            rows.append(future.result())

    df = pd.DataFrame(rows)
    df.to_csv(args.output, index=False)
    print(json.dumps({"runs": len(rows), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
