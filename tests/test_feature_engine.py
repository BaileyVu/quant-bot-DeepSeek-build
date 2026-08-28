"""Tests for feature engineering pipeline."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

from quantos.feature_engine.engine import FeatureEngine
from quantos.feature_engine.storage import FeatureStore
from quantos.config import get_config


@pytest.fixture
def sample_candle_df():
    """Generate a small set of synthetic candles for testing."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(minutes=i) for i in range(100)]
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 0.1)
    highs = prices + np.abs(np.random.randn(100) * 0.2)
    lows = prices - np.abs(np.random.randn(100) * 0.2)
    opens = prices - np.random.randn(100) * 0.05
    closes = prices + np.random.randn(100) * 0.05
    volumes = np.abs(np.random.randn(100) * 10 + 5)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    return df


def test_feature_computation_no_lookahead(sample_candle_df):
    """Ensure features only use past data."""
    engine = FeatureEngine()
    df = engine.compute_features(sample_candle_df, "BTCUSDT")
    # Check that first row has NaNs for rolling features
    first_row = df.iloc[0]
    # Some features like return_1 are NaN for row 0
    assert pd.isna(first_row["return_1"])
    # RSI requires at least 14 periods
    assert pd.isna(first_row["rsi_14"])
    # Volatility requires 10 periods
    assert pd.isna(first_row["volatility_10"])
    # MACD requires 26 periods for EMA
    assert pd.isna(first_row["macd_line"])
    # After enough history, values should be finite
    row_30 = df.iloc[30]
    assert not pd.isna(row_30["return_1"])
    assert not pd.isna(row_30["volatility_10"])
    assert not pd.isna(row_30["rsi_14"])
    assert not pd.isna(row_30["macd_line"])


def test_feature_engine_deterministic(sample_candle_df):
    """Running twice yields identical results."""
    engine = FeatureEngine()
    df1 = engine.compute_features(sample_candle_df, "BTCUSDT")
    df2 = engine.compute_features(sample_candle_df, "BTCUSDT")
    pd.testing.assert_frame_equal(df1, df2, check_dtype=False)


def test_duplicate_timestamp_raises(sample_candle_df):
    """Duplicate timestamps should raise an error."""
    df_dup = sample_candle_df.copy()
    # Duplicate the first row
    dup_row = df_dup.iloc[[0]].copy()
    df_dup = pd.concat([df_dup, dup_row], ignore_index=True)
    engine = FeatureEngine()
    with pytest.raises(ValueError, match="Duplicate timestamps"):
        engine.compute_features(df_dup, "BTCUSDT")


def test_missing_columns_raises(sample_candle_df):
    """Missing required columns should raise."""
    df_bad = sample_candle_df.drop(columns=["volume"])
    engine = FeatureEngine()
    with pytest.raises(ValueError, match="Missing required columns"):
        engine.compute_features(df_bad, "BTCUSDT")


def test_feature_store_save_load(tmp_path):
    """Test saving and loading features."""
    config = get_config()
    original_dir = config.data.parquet_dir
    # Override with temporary path
    config.data.parquet_dir = tmp_path
    store = FeatureStore()
    df = pd.DataFrame({
        "timestamp": [datetime(2025,1,1,0,0)],
        "symbol": ["BTCUSDT"],
        "version": ["v1.0"],
        "return_1": [0.01],
        "return_5": [0.05],
        "return_10": [0.10],
        "log_return_1": [0.0099],
        "volatility_10": [0.02],
        "rsi_14": [55.0],
        "macd_line": [0.5],
        "macd_signal": [0.4],
        "macd_histogram": [0.1],
        "volume_ratio_10": [1.2],
        "high_low_ratio": [0.01],
        "close_position_10": [0.8],
        "above_ma_20": [1.0],
    })
    count = store.save_features(df, symbol="BTCUSDT", version="v1.0")
    assert count == 1
    loaded = store.load_features("BTCUSDT", "v1.0")
    assert not loaded.empty
    assert loaded.iloc[0]["return_1"] == 0.01
    # Restore original dir (not required but good practice)
    config.data.parquet_dir = original_dir