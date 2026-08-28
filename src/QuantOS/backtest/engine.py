"""Main backtest engine: orchestrates data, model, portfolio simulation."""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from pathlib import Path
import pickle
import json
from loguru import logger

from quantos.config import get_config
from quantos.feature_engine.storage import FeatureStore
from quantos.model.artifacts import ModelArtifacts
from quantos.backtest.simulator import PortfolioSimulator
from quantos.backtest.metrics import PerformanceMetrics


class BacktestEngine:
    """
    Run a backtest for a given symbol using a trained model and feature data.
    """

    def __init__(
        self,
        symbol: str,
        version: str = "v1.0",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        self.config = get_config()
        self.symbol = symbol
        self.version = version
        self.start_time = start_time
        self.end_time = end_time

        # Load model artifacts
        self.artifacts = ModelArtifacts(symbol, version)
        self.model, self.feature_names, self.metadata = self.artifacts.load_model()

        # Load features for this symbol
        self.feature_store = FeatureStore()
        self.raw_features = self.feature_store.load_features(symbol, version)
        if self.raw_features.empty:
            raise ValueError(f"No features found for {symbol} version {version}")

        # Filter by time range
        self.df = self.raw_features.copy()
        if start_time:
            self.df = self.df[self.df["timestamp"] >= start_time]
        if end_time:
            self.df = self.df[self.df["timestamp"] <= end_time]
        self.df = self.df.sort_values("timestamp").reset_index(drop=True)

        # Ensure we have the required feature columns
        missing = set(self.feature_names) - set(self.df.columns)
        if missing:
            raise ValueError(f"Missing feature columns: {missing}")

        # Load candle data for this symbol
        from quantos.infrastructure.persistence import ParquetStore
        candle_store = ParquetStore()
        candles = candle_store.read_candles(symbol, start_time, end_time)
        if not candles:
            raise ValueError(f"No candle data found for {symbol}")
        candle_records = []
        for c in candles:
            candle_records.append({
                "timestamp": c.timestamp,
                "close": float(c.close),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "volume": float(c.volume),
            })
        self.candle_df = pd.DataFrame(candle_records)
        self.candle_df = self.candle_df.sort_values("timestamp").reset_index(drop=True)

        # Ensure no duplicate timestamps
        if self.df["timestamp"].duplicated().any():
            raise ValueError("Duplicate timestamps in feature data")
        if self.candle_df["timestamp"].duplicated().any():
            raise ValueError("Duplicate timestamps in candle data")

        # Merge features with close price on timestamp
        self.df = pd.merge(self.df, self.candle_df[["timestamp", "close"]], on="timestamp", how="inner")
        if self.df.empty:
            raise ValueError("No overlapping timestamps between features and candles")

        # Drop rows with NaN in features or close
        self.df = self.df.dropna(subset=self.feature_names + ["close"])
        self.df = self.df[np.isfinite(self.df["close"])]

        # Verify all rows belong to the correct symbol
        if "symbol" in self.df.columns:
            assert (self.df["symbol"] == symbol).all(), "Symbol mismatch in feature data"

        logger.info(f"Backtest data: {len(self.df)} rows from {self.df['timestamp'].min()} to {self.df['timestamp'].max()}")

    def run(self) -> Dict[str, Any]:
        """Execute the backtest loop."""
        config = self.config
        fee_bps = config.backtest.fee_bps
        slippage_bps = config.backtest.slippage_bps
        initial_capital = config.backtest.initial_capital

        sim = PortfolioSimulator(
            symbol=self.symbol,
            initial_capital=initial_capital,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )

        for idx, row in self.df.iterrows():
            timestamp = row["timestamp"]
            close_price = row["close"]
            X = row[self.feature_names].values.reshape(1, -1)
            prob = self.model.predict_proba(X)[0, 1]
            sim.update(timestamp, close_price, prob)

        if sim.trade_open and len(sim.history) > 0:
            last_row = self.df.iloc[-1]
            sim._exit(last_row["timestamp"], last_row["close"])

        results = sim.get_final_state()
        metrics = PerformanceMetrics.compute(results["equity_curve"], results["trades"], initial_capital)
        results["metrics"] = metrics
        results["config"] = {
            "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
            "initial_capital": initial_capital,
            "signal_threshold": config.backtest.signal_threshold,
        }
        results["symbol"] = self.symbol
        results["version"] = self.version
        results["start_time"] = self.df["timestamp"].min()
        results["end_time"] = self.df["timestamp"].max()
        results["data_sufficiency"] = {
            "total_rows": len(self.df),
            "feature_rows": len(self.df),
            "target_rows": len(self.df) - config.model.target_horizon,
            "num_trades": len(results["trades"]),
        }
        return results