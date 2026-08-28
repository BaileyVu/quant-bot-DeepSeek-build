"""Walk‑forward validation: train on expanding windows, test on subsequent periods."""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

from quantos.config import get_config
from quantos.feature_engine.storage import FeatureStore
from quantos.model.target import TargetCreator
from quantos.model.artifacts import ModelArtifacts
from quantos.backtest.simulator import PortfolioSimulator
from quantos.backtest.metrics import PerformanceMetrics


class WalkForwardValidator:
    """
    Perform walk‑forward validation by repeatedly training on expanding windows
    and testing on the following out‑of‑sample window.
    """

    def __init__(
        self,
        symbol: str,
        version: str = "v1.0",
        horizon: Optional[int] = None,
    ):
        self.config = get_config()
        self.symbol = symbol
        self.version = version
        self.horizon = horizon or self.config.model.target_horizon
        self.num_windows = self.config.backtest.walkforward_windows
        self.train_ratio = self.config.backtest.walkforward_train_ratio

        # Load full feature dataset for this symbol
        self.feature_store = FeatureStore()
        self.full_df = self.feature_store.load_features(symbol, version)
        if self.full_df.empty:
            raise ValueError(f"No features found for {symbol} version {version}")
        # Ensure sorted
        self.full_df = self.full_df.sort_values("timestamp").reset_index(drop=True)

        # Also load candle close prices for this symbol
        from quantos.infrastructure.persistence import ParquetStore
        candle_store = ParquetStore()
        candles = candle_store.read_candles(symbol)
        candle_records = []
        for c in candles:
            candle_records.append({
                "timestamp": c.timestamp,
                "close": float(c.close),
            })
        self.candle_df = pd.DataFrame(candle_records)
        self.candle_df = self.candle_df.sort_values("timestamp").reset_index(drop=True)

        # Merge features with close price
        self.df = pd.merge(self.full_df, self.candle_df[["timestamp", "close"]], on="timestamp", how="inner")
        self.df = self.df.dropna(subset=self.config.feature_engine.features + ["close"])
        self.df = self.df[np.isfinite(self.df["close"])]

        logger.info(f"Walk‑forward data for {symbol}: {len(self.df)} rows")

    def run(self) -> Dict[str, Any]:
        """
        Execute walk‑forward validation.
        Returns aggregated results and per‑window results.
        """
        results = []
        total_rows = len(self.df)
        if total_rows < 50:
            return {"status": "insufficient_data"}

        # Determine test window size
        test_size = total_rows // self.num_windows
        if test_size < 10:
            return {"status": "insufficient_data"}

        # Loop over windows
        for i in range(self.num_windows):
            min_train = int(total_rows * self.train_ratio)
            train_end = max(min_train, (i+1)*test_size)
            if train_end >= total_rows:
                break
            test_start = train_end
            test_end = min(test_start + test_size, total_rows)

            train_df = self.df.iloc[:train_end].copy()
            test_df = self.df.iloc[test_start:test_end].copy()
            if len(train_df) < 50 or len(test_df) < 10:
                break

            # Train a model on train_df
            import lightgbm as lgb
            from sklearn.metrics import accuracy_score, roc_auc_score

            target_creator = TargetCreator(self.horizon)
            target_train = target_creator.create_target(train_df)
            X_train = train_df[self.config.feature_engine.features].copy()
            y_train = target_train.loc[X_train.index]
            valid_idx = y_train.notna()
            X_train = X_train.loc[valid_idx]
            y_train = y_train.loc[valid_idx]
            X_train = X_train.dropna()
            y_train = y_train.loc[X_train.index]

            if len(X_train) < 50:
                break

            # Model params (fixed)
            model_params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "boosting_type": "gbdt",
                "num_leaves": 31,
                "max_depth": 6,
                "learning_rate": 0.05,
                "n_estimators": 200,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.1,
                "reg_lambda": 0.1,
                "min_child_samples": 20,
                "random_state": self.config.model.random_seed,
                "verbosity": -1,
            }
            model = lgb.LGBMClassifier(**model_params)
            model.fit(X_train, y_train)

            # Now evaluate on test set using the PortfolioSimulator
            # Prepare test data: need to generate predictions sequentially
            sim = PortfolioSimulator(
                symbol=self.symbol,
                initial_capital=self.config.backtest.initial_capital,
                fee_bps=self.config.backtest.fee_bps,
                slippage_bps=self.config.backtest.slippage_bps,
            )
            threshold = self.config.backtest.signal_threshold
            for idx, row in test_df.iterrows():
                timestamp = row["timestamp"]
                close_price = row["close"]
                X_row = row[self.config.feature_engine.features].values.reshape(1, -1)
                # Predict probability
                prob = model.predict_proba(X_row)[0, 1]
                sim.update(timestamp, close_price, prob)

            # Close any open position
            if sim.trade_open and len(sim.history) > 0:
                last_row = test_df.iloc[-1]
                sim._exit(last_row["timestamp"], last_row["close"])

            final_state = sim.get_final_state()
            metrics = PerformanceMetrics.compute(final_state["equity_curve"], final_state["trades"], self.config.backtest.initial_capital)

            window_result = {
                "window": i,
                "train_start": train_df["timestamp"].min().isoformat(),
                "train_end": train_df["timestamp"].max().isoformat(),
                "test_start": test_df["timestamp"].min().isoformat(),
                "test_end": test_df["timestamp"].max().isoformat(),
                "n_train": len(train_df),
                "n_test": len(test_df),
                "metrics": metrics,
                "num_trades": final_state["num_trades"],
            }
            results.append(window_result)

        if not results:
            return {"status": "no_valid_windows"}

        # Aggregate metrics
        agg_metrics = {}
        metric_keys = ["total_return_pct", "sharpe_ratio", "sortino_ratio", "max_drawdown_pct",
                       "profit_factor", "win_rate", "num_trades", "avg_trade_pnl", "exposure_pct", "expected_value"]
        for key in metric_keys:
            values = [r["metrics"].get(key, 0.0) for r in results if "metrics" in r and key in r["metrics"]]
            if values:
                agg_metrics[f"avg_{key}"] = np.mean(values)
                agg_metrics[f"std_{key}"] = np.std(values)
            else:
                agg_metrics[f"avg_{key}"] = None
                agg_metrics[f"std_{key}"] = None

        return {
            "status": "success",
            "num_windows": len(results),
            "windows": results,
            "aggregated": agg_metrics,
        }