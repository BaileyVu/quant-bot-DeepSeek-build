"""Monte Carlo simulation on trade sequence."""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from quantos.config import get_config
from quantos.backtest.metrics import PerformanceMetrics


class MonteCarloSimulator:
    """
    Perform Monte Carlo simulation by resampling the realized trade sequence
    to generate distributions of performance metrics.
    """

    def __init__(self, trades: List, initial_capital: float, symbol: str):
        self.trades = trades
        self.initial_capital = initial_capital
        self.symbol = symbol
        self.config = get_config()
        self.n_iter = self.config.backtest.monte_carlo_iterations
        self.seed = self.config.backtest.monte_carlo_seed
        np.random.seed(self.seed)

        # Validate all trades have the same symbol as this simulator
        if trades:
            trade_symbols = set(t.symbol for t in trades)
            if len(trade_symbols) > 1:
                raise ValueError(f"Multiple symbols in trades: {trade_symbols}")
            if trade_symbols and self.symbol not in trade_symbols:
                raise ValueError(f"Trade symbol mismatch: expected {self.symbol}, got {trade_symbols}")

    def run(self) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation.
        Returns distributions of key metrics.
        """
        if not self.trades:
            return {"status": "insufficient_data"}

        # Extract net PnL from each trade
        pnls = [t.net_pnl for t in self.trades]
        n_trades = len(pnls)

        sim_results = []
        for _ in range(self.n_iter):
            sampled_pnls = np.random.choice(pnls, size=n_trades, replace=True)
            cum_pnl = np.cumsum(sampled_pnls)
            final_equity = self.initial_capital + cum_pnl[-1]
            # Create a dummy equity curve with one point per trade
            timestamps = [datetime(2025, i+1, 1) for i in range(n_trades)]  # dummy
            equity_vals = self.initial_capital + np.concatenate([[0], np.cumsum(sampled_pnls)])
            equity_curve = pd.DataFrame({
                "timestamp": timestamps,
                "equity": equity_vals[:-1]
            })
            # Compute win rate from sampled pnls
            winning = sum(1 for p in sampled_pnls if p > 0)
            win_rate = winning / n_trades
            total_return_pct = (final_equity / self.initial_capital - 1) * 100
            # We'll compute simplified metrics
            sim_results.append({
                "final_equity": final_equity,
                "total_return_pct": total_return_pct,
                "win_rate": win_rate,
                "avg_trade_pnl": np.mean(sampled_pnls),
                "std_trade_pnl": np.std(sampled_pnls),
            })

        if not sim_results:
            return {"status": "no_simulations"}

        df_sim = pd.DataFrame(sim_results)
        quantiles = [0.05, 0.25, 0.5, 0.75, 0.95]
        agg = {}
        for col in df_sim.columns:
            if col in ["num_trades"]:
                continue
            agg[col] = {
                "mean": df_sim[col].mean(),
                "std": df_sim[col].std(),
                "q05": df_sim[col].quantile(0.05),
                "q25": df_sim[col].quantile(0.25),
                "q50": df_sim[col].quantile(0.5),
                "q75": df_sim[col].quantile(0.75),
                "q95": df_sim[col].quantile(0.95),
            }

        return {
            "status": "success",
            "n_iterations": self.n_iter,
            "seed": self.seed,
            "n_trades_original": n_trades,
            "distributions": agg,
        }