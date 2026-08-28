"""Tests for paper trading runtime."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from quantos.paper.runtime import PaperRuntime
from quantos.paper.portfolio import PaperPortfolio
from quantos.paper.risk import RiskEngine
from quantos.domain.candle import Candle
from quantos.config import get_config


@pytest.fixture
def sample_candle_sequence():
    """Generate a sequence of synthetic candles."""
    base = datetime(2025, 1, 1, 0, 0)
    candles = []
    for i in range(30):
        ts = base + timedelta(minutes=i)
        c = Candle(
            symbol="BTCUSDT",
            interval="1m",
            timestamp=ts,
            open=100 + i*0.1,
            high=100 + i*0.1 + 0.2,
            low=100 + i*0.1 - 0.1,
            close=100 + i*0.1 + 0.05,
            volume=10 + i,
        )
        candles.append(c)
    return candles


def test_paper_portfolio_basic():
    portfolio = PaperPortfolio(initial_capital=100.0, fee_bps=10, slippage_bps=5)
    # Enter
    portfolio.update("BTCUSDT", price=100, signal=0.8, threshold=0.5)
    assert "BTCUSDT" in portfolio.positions
    assert portfolio.positions["BTCUSDT"] > 0
    # Exit
    portfolio.update("BTCUSDT", price=101, signal=0.2, threshold=0.5)
    assert "BTCUSDT" not in portfolio.positions
    assert len(portfolio.trades) == 1
    trade = portfolio.trades[0]
    assert trade.net_pnl > 0  # should be positive


def test_risk_engine():
    risk = RiskEngine()
    # Check that order within limits passes
    assert risk.check_order("BTCUSDT", 100, 0.1, 100, {}) == True
    # Check that notional exceeds max
    risk.max_position_notional = 10
    assert risk.check_order("BTCUSDT", 100, 0.5, 100, {}) == False


def test_paper_runtime_acceptance(sample_candle_sequence, monkeypatch):
    """Deterministic test without Binance."""
    # We'll mock the live market data to feed candles.
    # But the runtime uses LiveMarketData which connects to Binance.
    # We'll patch the LiveMarketData to use our sample candles.
    from quantos.market_data.live import LiveMarketData
    original_init = LiveMarketData.__init__
    def mock_init(self, symbol, interval="1m"):
        self.symbol = symbol
        self.interval = interval
        self.callbacks = []
        self._running = False
    LiveMarketData.__init__ = mock_init

    # We also need to override the on_candle method to call callbacks immediately
    def mock_start(self):
        # Simulate processing each candle
        for candle in sample_candle_sequence:
            for cb in self.callbacks:
                cb(candle)
    LiveMarketData.start = mock_start

    # Also need to mock the model load – we'll create a dummy model
    # We'll patch ModelArtifacts.load_model to return a dummy predictor
    from quantos.model.artifacts import ModelArtifacts
    original_load = ModelArtifacts.load_model
    def mock_load_model(self):
        # Return a dummy model that always predicts 0.6
        class DummyModel:
            def predict_proba(self, X):
                return np.array([[0.4, 0.6]])
        return DummyModel(), self.feature_names, {"horizon": 5}
    ModelArtifacts.load_model = mock_load_model

    # Patch FeatureEngine.compute_features to return a DataFrame with features
    from quantos.feature_engine.engine import FeatureEngine
    original_compute = FeatureEngine.compute_features
    def mock_compute_features(self, df, symbol):
        # Create a dummy feature DataFrame
        df_out = df[["timestamp"]].copy()
        for f in self.feature_names:
            df_out[f] = 0.5  # constant
        df_out["symbol"] = symbol
        df_out["version"] = self.version
        return df_out
    FeatureEngine.compute_features = mock_compute_features

    # Now we can run the runtime
    runtime = PaperRuntime("BTCUSDT", "v1.0")
    # We'll run it with a mock loop that stops after processing all candles
    # For test, we'll just call start and then stop after a short time
    runtime.start()
    # Wait a bit for processing
    import time
    time.sleep(1)
    runtime.stop()
    # Verify that portfolio has some trades
    assert len(runtime.portfolio.trades) > 0
    # Restore original methods
    LiveMarketData.__init__ = original_init
    ModelArtifacts.load_model = original_load
    FeatureEngine.compute_features = original_compute

def test_safety_barrier():
    from quantos.paper.safety import SafetyBarrier
    barrier = SafetyBarrier()
    # Should raise if order attempted
    with pytest.raises(RuntimeError):
        barrier.check("limit", "BTCUSDT", "BUY", 0.1)