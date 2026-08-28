"""Tests for backtesting module."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

from quantos.backtest.simulator import PortfolioSimulator
from quantos.backtest.engine import BacktestEngine
from quantos.backtest.metrics import PerformanceMetrics
from quantos.backtest.walkforward import WalkForwardValidator
from quantos.backtest.montecarlo import MonteCarloSimulator
from quantos.config import get_config
from quantos.feature_engine.storage import FeatureStore
from quantos.model.artifacts import ModelArtifacts


@pytest.fixture
def sample_feature_df():
    """Create synthetic feature data with close price."""
    np.random.seed(42)
    base = datetime(2025, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=i) for i in range(200)]
    close = 100 + np.cumsum(np.random.randn(200) * 0.1)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "symbol": ["BTCUSDT"] * 200,
        "version": ["v1.0"] * 200,
        "return_1": np.random.randn(200) * 0.01,
        "return_5": np.random.randn(200) * 0.02,
        "return_10": np.random.randn(200) * 0.03,
        "log_return_1": np.random.randn(200) * 0.01,
        "volatility_10": np.abs(np.random.randn(200) * 0.02),
        "rsi_14": np.random.uniform(30, 70, 200),
        "macd_line": np.random.randn(200) * 0.5,
        "macd_signal": np.random.randn(200) * 0.5,
        "macd_histogram": np.random.randn(200) * 0.2,
        "volume_ratio_10": np.random.uniform(0.5, 1.5, 200),
        "high_low_ratio": np.abs(np.random.randn(200) * 0.01),
        "close_position_10": np.random.uniform(0, 1, 200),
        "above_ma_20": np.random.randint(0, 2, 200),
        "close": close,
    })
    return df


def test_portfolio_simulator_basic():
    sim = PortfolioSimulator(initial_capital=100.0, fee_bps=10, slippage_bps=5)
    # Enter at price 10
    sim._enter(datetime(2025,1,1,0,0), price=10)
    assert sim.trade_open is True
    assert sim.position > 0
    # Exit at price 11
    sim._exit(datetime(2025,1,1,0,5), price=11)
    assert sim.trade_open is False
    assert sim.position == 0
    # Check that PnL is positive
    trade = sim.trades[0]
    assert trade.net_pnl > 0
    # Check that fee and slippage were applied
    assert trade.fee_entry > 0
    assert trade.fee_exit > 0
    assert trade.slippage_entry > 0
    assert trade.slippage_exit > 0


def test_metrics_computation(tmp_path):
    # Create equity curve
    timestamps = [datetime(2025,1,1,0,i) for i in range(10)]
    equity = [100, 101, 102, 101, 100, 99, 100, 101, 102, 103]
    equity_curve = pd.DataFrame({"timestamp": timestamps, "equity": equity})
    trades = []  # dummy
    metrics = PerformanceMetrics.compute(equity_curve, trades, initial_capital=100)
    assert metrics["total_return_pct"] == 3.0
    assert metrics["num_trades"] == 0
    assert "sharpe_ratio" in metrics


def test_backtest_engine_integration(tmp_path, sample_feature_df, monkeypatch):
    # Override data dir to temp
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    cfg.data.parquet_dir = tmp_path

    # Store features and train a model
    store = FeatureStore()
    store.save_features(sample_feature_df, symbol="BTCUSDT", version="v1.0")

    # Train a dummy model (we need a model artifact)
    from lightgbm import LGBMClassifier
    X = sample_feature_df[cfg.feature_engine.features].dropna()
    y = np.random.randint(0, 2, len(X))
    model = LGBMClassifier(n_estimators=2, random_state=42)
    model.fit(X, y)
    artifacts = ModelArtifacts("BTCUSDT", "v1.0")
    artifacts.save_model(model, cfg.feature_engine.features, {"horizon": 5})

    # Run backtest
    engine = BacktestEngine("BTCUSDT", "v1.0")
    result = engine.run()
    assert "metrics" in result
    assert "num_trades" in result
    # Reset config dir
    cfg.data.parquet_dir = original_dir


def test_walkforward(tmp_path, sample_feature_df, monkeypatch):
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    cfg.data.parquet_dir = tmp_path

    # Store features and train a model (but walkforward will retrain)
    store = FeatureStore()
    store.save_features(sample_feature_df, symbol="BTCUSDT", version="v1.0")

    # We need to ensure there are enough rows for walkforward.
    # The sample has 200 rows, with 3 windows -> each test size ~66, fine.
    wf = WalkForwardValidator("BTCUSDT", "v1.0", horizon=5)
    result = wf.run()
    assert result["status"] in ["success", "no_valid_windows"]  # if we have enough data
    if result["status"] == "success":
        assert "num_windows" in result

    cfg.data.parquet_dir = original_dir


def test_montecarlo():
    # Create dummy trades
    trades = []
    from quantos.backtest.simulator import Trade
    for i in range(10):
        t = Trade(
            entry_time=datetime(2025,1,1,0,i),
            entry_price=100,
            exit_time=datetime(2025,1,1,0,i+1),
            exit_price=100 + np.random.randn()*2,
            size=1,
            fee_entry=0.01,
            fee_exit=0.01,
            slippage_entry=0.005,
            slippage_exit=0.005,
            gross_pnl=0.0,
            net_pnl=np.random.randn()*2,
            direction="long",
        )
        trades.append(t)
    monte = MonteCarloSimulator(trades, initial_capital=100)
    result = monte.run()
    assert result["status"] == "success"
    assert result["n_iterations"] == 100  # default config
    assert "distributions" in result

def test_symbol_isolation(tmp_path, monkeypatch):
    """Test that BTC and ETH backtests do not mix prices."""
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    cfg.data.parquet_dir = tmp_path

    # Create synthetic data for BTC and ETH with different price levels
    import numpy as np
    base = datetime(2025,1,1,0,0)
    timestamps = [base + timedelta(minutes=i) for i in range(200)]
    btc_prices = 50000 + np.cumsum(np.random.randn(200)*10)
    eth_prices = 2000 + np.cumsum(np.random.randn(200)*5)

    # Create feature DataFrames for each symbol (using the same feature columns)
    feature_cols = cfg.feature_engine.features
    df_btc = pd.DataFrame({
        "timestamp": timestamps,
        "symbol": "BTCUSDT",
        "version": "v1.0",
        **{f: np.random.randn(200)*0.01 for f in feature_cols},
        "close": btc_prices,
    })
    df_eth = pd.DataFrame({
        "timestamp": timestamps,
        "symbol": "ETHUSDT",
        "version": "v1.0",
        **{f: np.random.randn(200)*0.01 for f in feature_cols},
        "close": eth_prices,
    })

    # Store features
    store = FeatureStore()
    store.save_features(df_btc, "BTCUSDT", "v1.0")
    store.save_features(df_eth, "ETHUSDT", "v1.0")

    # Store candles (we also need to store candles separately for the backtest engine)
    from quantos.infrastructure.persistence import ParquetStore
    candle_store = ParquetStore()
    # Convert to candles (but we can just store as parquet directly? The engine reads via ParquetStore.read_candles, which reads from parquet files. We need to create those files.)
    # We'll create candle data by using the same data but we need to write to the parquet directory.
    # The engine reads from the parquet directory using ParquetStore. We'll store the candles using the same method.
    # Actually, the engine loads candles via ParquetStore.read_candles, which reads from the symbol's parquet file.
    # So we need to write candle DataFrames to the same directory.
    # We'll reuse the candle_store but it expects candles to be written via append_candles.
    # We'll convert the data to candle objects.
    from quantos.domain.candle import Candle
    from decimal import Decimal
    candles_btc = []
    for i, row in df_btc.iterrows():
        c = Candle(
            symbol="BTCUSDT",
            interval="1m",
            timestamp=row["timestamp"],
            open=Decimal(row["close"] - np.random.randn()*0.5),
            high=Decimal(row["close"] + abs(np.random.randn()*0.5)),
            low=Decimal(row["close"] - abs(np.random.randn()*0.5)),
            close=Decimal(row["close"]),
            volume=Decimal(np.random.rand()*10),
        )
        candles_btc.append(c)
    candle_store.append_candles(candles_btc)
    # Similarly for ETH
    candles_eth = []
    for i, row in df_eth.iterrows():
        c = Candle(
            symbol="ETHUSDT",
            interval="1m",
            timestamp=row["timestamp"],
            open=Decimal(row["close"] - np.random.randn()*0.5),
            high=Decimal(row["close"] + abs(np.random.randn()*0.5)),
            low=Decimal(row["close"] - abs(np.random.randn()*0.5)),
            close=Decimal(row["close"]),
            volume=Decimal(np.random.rand()*10),
        )
        candles_eth.append(c)
    candle_store.append_candles(candles_eth)

    # Train a dummy model for each symbol (we need a model artifact)
    from lightgbm import LGBMClassifier
    X_btc = df_btc[feature_cols].dropna()
    y_btc = np.random.randint(0,2,len(X_btc))
    model_btc = LGBMClassifier(n_estimators=2, random_state=42)
    model_btc.fit(X_btc, y_btc)
    artifacts_btc = ModelArtifacts("BTCUSDT", "v1.0")
    artifacts_btc.save_model(model_btc, feature_cols, {"horizon": 5})

    X_eth = df_eth[feature_cols].dropna()
    y_eth = np.random.randint(0,2,len(X_eth))
    model_eth = LGBMClassifier(n_estimators=2, random_state=42)
    model_eth.fit(X_eth, y_eth)
    artifacts_eth = ModelArtifacts("ETHUSDT", "v1.0")
    artifacts_eth.save_model(model_eth, feature_cols, {"horizon": 5})

    # Now run backtest for BTC
    engine_btc = BacktestEngine("BTCUSDT", "v1.0")
    result_btc = engine_btc.run()
    # All trades should have symbol BTCUSDT
    for trade in result_btc["trades"]:
        assert trade.symbol == "BTCUSDT"
    # Check that entry and exit prices are around 50000, not 2000
    if result_btc["trades"]:
        avg_entry = np.mean([t.entry_price for t in result_btc["trades"]])
        assert abs(avg_entry - 50000) < 1000, f"BTC trade entry price {avg_entry} is not near 50000"

    # Run backtest for ETH
    engine_eth = BacktestEngine("ETHUSDT", "v1.0")
    result_eth = engine_eth.run()
    for trade in result_eth["trades"]:
        assert trade.symbol == "ETHUSDT"
    if result_eth["trades"]:
        avg_entry = np.mean([t.entry_price for t in result_eth["trades"]])
        assert abs(avg_entry - 2000) < 100, f"ETH trade entry price {avg_entry} is not near 2000"

    cfg.data.parquet_dir = original_dir