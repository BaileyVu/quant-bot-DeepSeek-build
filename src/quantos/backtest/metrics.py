"""Performance metrics calculation for backtest results."""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from scipy.stats import norm
import math


class PerformanceMetrics:
    """Compute standard performance metrics from equity curve and trades."""

    @staticmethod
    def compute(equity_curve: pd.DataFrame, trades: List, initial_capital: float) -> Dict[str, Any]:
        """
        Compute all required metrics.

        Parameters
        ----------
        equity_curve : pd.DataFrame with columns 'timestamp' and 'equity'
        trades : list of Trade objects
        initial_capital : float

        Returns
        -------
        dict with all metrics (returns as percentages where appropriate)
        """
        if equity_curve.empty:
            return {"status": "insufficient_data"}

        # Ensure equity_curve is sorted
        equity_curve = equity_curve.sort_values("timestamp").reset_index(drop=True)

        # Total return
        final_equity = equity_curve["equity"].iloc[-1]
        total_return_pct = (final_equity / initial_capital - 1) * 100

        # Net profit
        net_profit = final_equity - initial_capital

        # Number of trades
        num_trades = len(trades)

        # Win rate
        if num_trades > 0:
            winning_trades = [t for t in trades if t.net_pnl > 0]
            win_rate = len(winning_trades) / num_trades
            avg_trade_pnl = sum(t.net_pnl for t in trades) / num_trades
            avg_win = sum(t.net_pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
            avg_loss = sum(t.net_pnl for t in trades if t.net_pnl <= 0) / (num_trades - len(winning_trades)) if (num_trades - len(winning_trades)) > 0 else 0.0
            profit_factor = sum(t.net_pnl for t in trades if t.net_pnl > 0) / abs(sum(t.net_pnl for t in trades if t.net_pnl < 0)) if any(t.net_pnl < 0 for t in trades) else float('inf')
        else:
            win_rate = 0.0
            avg_trade_pnl = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            profit_factor = 0.0

        # Calculate daily returns (assuming 1-minute data, we can resample to daily)
        # For simplicity, we compute returns on each bar and annualize.
        # We'll compute returns as percentage change in equity
        returns = equity_curve["equity"].pct_change().dropna()
        if len(returns) == 0:
            sharpe = 0.0
            sortino = 0.0
        else:
            # Assuming 1-minute bars, annualization factor: ~525600 minutes per year (365*24*60)
            annual_factor = 365 * 24 * 60
            # Sharpe ratio (risk-free rate = 0)
            mean_return = returns.mean()
            std_return = returns.std()
            if std_return > 0:
                sharpe = mean_return / std_return * np.sqrt(annual_factor)
            else:
                sharpe = 0.0
            # Sortino ratio (downside deviation)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0:
                downside_std = downside_returns.std()
                sortino = mean_return / downside_std * np.sqrt(annual_factor) if downside_std > 0 else 0.0
            else:
                sortino = 0.0

        # Maximum drawdown (should be <= 0)
        max_equity = equity_curve["equity"].expanding().max()
        drawdown = (equity_curve["equity"] - max_equity) / max_equity
        max_drawdown_pct = drawdown.min() * 100  # negative percentage

        # Exposure: percentage of time in the market
        total_duration = (equity_curve["timestamp"].iloc[-1] - equity_curve["timestamp"].iloc[0]).total_seconds()
        if total_duration == 0 or num_trades == 0:
            exposure_pct = 0.0
        else:
            in_market_seconds = 0.0
            for trade in trades:
                if trade.exit_time and trade.entry_time:
                    in_market_seconds += (trade.exit_time - trade.entry_time).total_seconds()
            exposure_pct = (in_market_seconds / total_duration) * 100

        # Expected Value per trade (average net pnl)
        expected_value = avg_trade_pnl if num_trades > 0 else 0.0

        return {
            "total_return_pct": total_return_pct,
            "net_profit": net_profit,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": max_drawdown_pct,  # negative
            "profit_factor": profit_factor,
            "win_rate": win_rate,
            "num_trades": num_trades,
            "avg_trade_pnl": avg_trade_pnl,
            "exposure_pct": exposure_pct,
            "expected_value": expected_value,
            "final_equity": final_equity,
            "initial_capital": initial_capital,
        }