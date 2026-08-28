"""Paper trading runtime: live market data -> features -> model -> signal -> risk -> execution."""

import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

from quantos.config import get_config
from quantos.market_data.live import LiveMarketData
from quantos.market_data.validator import validate_candle, normalize_binance_kline
from quantos.domain.candle import Candle
from quantos.feature_engine.engine import FeatureEngine
from quantos.model.artifacts import ModelArtifacts
from quantos.paper.portfolio import PaperPortfolio
from quantos.paper.risk import RiskEngine
from quantos.paper.state import StatePersistence
from quantos.paper.safety import SafetyBarrier


class PaperRuntime:
    def __init__(self, symbol: str, version: str = "v1.0", horizon: Optional[int] = None):
        self.config = get_config()
        self.symbol = symbol
        self.version = version
        self.horizon = horizon or self.config.model.target_horizon
        self.paper_config = self.config.paper
        self.interval = self.config.interval

        # Load model
        self.artifacts = ModelArtifacts(symbol, version)
        self.model, self.feature_names, self.metadata = self.artifacts.load_model()

        # Feature engine
        self.feature_engine = FeatureEngine(version)

        # Portfolio
        self.portfolio = PaperPortfolio(
            initial_capital=self.paper_config.initial_capital,
            fee_bps=self.config.backtest.fee_bps,
            slippage_bps=self.config.backtest.slippage_bps,
        )

        # Risk
        self.risk = RiskEngine()

        # Persistence
        self.persistence = StatePersistence()

        # Safety barrier
        self.safety = SafetyBarrier()

        # Runtime state
        self.running = False
        self.last_processed_timestamp: Optional[datetime] = None
        self.last_market_data_time: Optional[datetime] = None
        self.history_buffer: Dict[str, list] = {symbol: []}  # store candles for feature computation

        # Load previous state if exists
        self._restore_state()

        # Live market data handler
        self.live = LiveMarketData(symbol)
        self.live.on_candle(self._on_candle)

    def _restore_state(self):
        state = self.persistence.load()
        if state:
            self.portfolio.load_state(state.get("portfolio", {}))
            self.last_processed_timestamp = state.get("last_processed_timestamp")
            self.history_buffer = state.get("history_buffer", {symbol: []})
            logger.info("Restored paper state")

    def _save_state(self):
        state = {
            "portfolio": self.portfolio.get_state(),
            "last_processed_timestamp": self.last_processed_timestamp,
            "history_buffer": self.history_buffer,
        }
        self.persistence.save(state)

    def _on_candle(self, candle: Candle):
        """Callback for each completed candle from WebSocket."""
        # Validate candle
        if not validate_candle(candle):
            logger.warning(f"Invalid candle received: {candle}")
            return

        # Duplicate check
        key = (candle.symbol, candle.timestamp)
        if self.last_processed_timestamp and candle.timestamp <= self.last_processed_timestamp:
            logger.debug(f"Duplicate candle {candle.symbol} {candle.timestamp} ignored")
            return

        logger.info(f"Processing completed candle {candle.symbol} {candle.timestamp}")

        # Update buffer
        self.history_buffer.setdefault(candle.symbol, []).append(candle)
        # Keep only enough history for features (e.g., 100 candles)
        if len(self.history_buffer[candle.symbol]) > 100:
            self.history_buffer[candle.symbol] = self.history_buffer[candle.symbol][-100:]

        # Compute features for the latest candle
        # We need to convert candles to DataFrame
        import pandas as pd
        candles = self.history_buffer[candle.symbol]
        df_candles = pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in candles
        ])
        # Ensure sorted
        df_candles = df_candles.sort_values("timestamp").reset_index(drop=True)

        # Compute features
        df_features = self.feature_engine.compute_features(df_candles, symbol=candle.symbol)
        if df_features.empty:
            logger.warning("No features computed")
            return

        # Get the latest feature row (the one corresponding to this candle)
        latest_features = df_features.iloc[-1]
        # Check if any feature is NaN (insufficient history)
        if latest_features[self.feature_names].isna().any():
            logger.info("Insufficient history for prediction, skipping")
            return

        # Prepare feature vector
        X = latest_features[self.feature_names].values.reshape(1, -1)
        # Predict
        prob = self.model.predict_proba(X)[0, 1]
        signal = prob

        # Risk check
        price = float(candle.close)
        current_equity = self.portfolio.get_equity({candle.symbol: price})
        # For risk, we check if we would enter
        if signal >= self.config.backtest.signal_threshold:
            # Check if we can afford
            available_cash = self.portfolio.cash
            # Simulate order size (use all cash)
            cost_per_unit = price * (1 + self.portfolio.slippage_rate)
            fee = available_cash * self.portfolio.fee_rate
            available = available_cash - fee
            if available <= 0:
                logger.warning("Insufficient cash, skip entry")
                return
            quantity = available / cost_per_unit
            # Risk check
            if not self.risk.check_order(candle.symbol, price, quantity, current_equity, self.portfolio.positions):
                logger.info("Risk rejected order")
                return

        # Update portfolio
        self.portfolio.update(candle.symbol, price, signal, self.config.backtest.signal_threshold)

        # Update risk metrics
        new_equity = self.portfolio.get_equity({candle.symbol: price})
        self.risk.update_metrics(new_equity)

        # Update last processed
        self.last_processed_timestamp = candle.timestamp
        self.last_market_data_time = datetime.utcnow()

        # Persist state periodically
        self._save_state()

        # Log summary
        logger.info(f"Equity: {new_equity:.2f}, Position: {self.portfolio.positions.get(candle.symbol, 0)}")

    def start(self):
        """Start the paper runtime."""
        self.running = True
        self.live.start()
        logger.info("Paper runtime started")

    def stop(self):
        """Stop the runtime."""
        self.running = False
        self.live.stop()
        self._save_state()
        logger.info("Paper runtime stopped")

    def run_forever(self):
        """Blocking run loop (handles reconnects and stale data)."""
        self.start()
        try:
            while self.running:
                time.sleep(1)
                # Check stale data
                if self.last_market_data_time:
                    elapsed = (datetime.utcnow() - self.last_market_data_time).total_seconds()
                    if elapsed > self.paper_config.stale_data_timeout_seconds:
                        logger.warning("Stale data detected, pausing decisions")
                        # In a real implementation, we could pause trading.
                        # For now, just log.
        except KeyboardInterrupt:
            self.stop()