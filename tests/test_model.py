"""Tests for model training pipeline."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

from quantos.model.target import TargetCreator
from quantos.model.trainer import ModelTrainer
from quantos.model.artifacts import ModelArtifacts
from quantos.feature_engine.storage import FeatureStore
from quantos.config import get_config


@pytest.fixture
def sample_feature_df():
    """Create a minimal feature DataFrame for testing."""
    base = datetime(2025, 1, 1, 0, 0, 0)
    timestamps = [base + timedelta(minutes=i) for i in range(100)]
    np.random.seed(42)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "symbol": ["BTCUSDT"] * 100,
        "version": ["v1.0"] * 100,
        "return_1": np.random.randn(100) * 0.01,
        "return_5": np.random.randn(100) * 0.02,
        "return_10": np.random.randn(100) * 0.03,
        "log_return_1": np.random.randn(100) * 0.01,
        "volatility_10": np.abs(np.random.randn(100) * 0.02),
        "rsi_14": np.random.uniform(30, 70, 100),
        "macd_line": np.random.randn(100) * 0.5,
        "macd_signal": np.random.randn(100) * 0.5,
        "macd_histogram": np.random.randn(100) * 0.2,
        "volume_ratio_10": np.random.uniform(0.5, 1.5, 100),
        "high_low_ratio": np.abs(np.random.randn(100) * 0.01),
        "close_position_10": np.random.uniform(0, 1, 100),
        "above_ma_20": np.random.randint(0, 2, 100),
        "close": 100 + np.cumsum(np.random.randn(100) * 0.1),
    })
    return df


def test_target_creation(sample_feature_df):
    target_creator = TargetCreator(horizon=3)
    target = target_creator.create_target(sample_feature_df)
    # Expect NaN for last 3 rows
    assert target.iloc[-1] is np.nan
    assert target.iloc[-2] is np.nan
    assert target.iloc[-3] is np.nan
    # First few should not be NaN (if data sufficient)
    assert not pd.isna(target.iloc[0])


def test_target_no_lookahead(sample_feature_df):
    # Ensure target uses only future data, but we test that it's computed correctly.
    target_creator = TargetCreator(horizon=2)
    target = target_creator.create_target(sample_feature_df)
    # At index 0, target should be based on close[2] vs close[0]
    close0 = sample_feature_df["close"].iloc[0]
    close2 = sample_feature_df["close"].iloc[2]
    expected = 1.0 if close2 > close0 else 0.0
    assert target.iloc[0] == expected


def test_trainer_split(sample_feature_df, tmp_path, monkeypatch):
    # Override data dir to tmp_path so we can save features for testing
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    cfg.data.parquet_dir = tmp_path

    # Store features to disk
    store = FeatureStore()
    store.save_features(sample_feature_df, symbol="BTCUSDT", version="v1.0")

    # Now instantiate trainer and test split
    trainer = ModelTrainer("BTCUSDT", "v1.0", horizon=3)
    df = trainer.load_data()
    train_df, val_df, holdout_df = trainer.split_data(df)
    # Check chronological order and sizes
    assert len(train_df) > 0
    assert len(val_df) > 0
    assert len(holdout_df) > 0
    # Check that train ends before val starts, etc.
    assert train_df["timestamp"].max() < val_df["timestamp"].min()
    assert val_df["timestamp"].max() < holdout_df["timestamp"].min()

    # Restore original dir
    cfg.data.parquet_dir = original_dir


def test_trainer_prepare_features_target(sample_feature_df):
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    # We'll just test the method directly with sample data
    trainer = ModelTrainer("BTCUSDT", "v1.0", horizon=3)
    X, y = trainer.prepare_features_target(sample_feature_df)
    # Should have dropped rows with NaN target (last 3)
    assert len(X) == len(sample_feature_df) - 3
    # Features should be the ones defined in config
    expected_features = cfg.feature_engine.features
    assert set(X.columns) == set(expected_features)
    # No NaN in X or y
    assert not X.isna().any().any()
    assert y.isna().sum() == 0


def test_artifacts_save_load(sample_feature_df, tmp_path, monkeypatch):
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    cfg.data.parquet_dir = tmp_path

    # Create a dummy model (not trained, but we can save a placeholder)
    from lightgbm import LGBMClassifier
    model = LGBMClassifier(n_estimators=2)
    # Fake training: just fit on a small subset
    X = sample_feature_df[cfg.feature_engine.features].iloc[:10]
    y = np.random.randint(0, 2, 10)
    model.fit(X, y)

    artifacts = ModelArtifacts("BTCUSDT", "v1.0")
    feature_names = cfg.feature_engine.features
    metadata = {
        "horizon": 5,
        "train_start": datetime(2025,1,1),
        "train_end": datetime(2025,1,10),
        "val_start": datetime(2025,1,11),
        "val_end": datetime(2025,1,20),
        "holdout_start": None,
        "holdout_end": None,
        "metrics": {"train_accuracy": 0.8},
        "random_seed": 42,
    }
    artifacts.save_model(model, feature_names, metadata)

    # Load back
    loaded_model, loaded_features, loaded_metadata = artifacts.load_model()
    assert loaded_features == feature_names
    assert loaded_metadata["horizon"] == 5
    # Check that model can predict
    pred = loaded_model.predict(X)
    assert len(pred) == len(X)

    cfg.data.parquet_dir = original_dir


def test_full_train_pipeline(sample_feature_df, tmp_path, monkeypatch):
    """Integration test: end-to-end training on synthetic data."""
    cfg = get_config()
    original_dir = cfg.data.parquet_dir
    cfg.data.parquet_dir = tmp_path

    # Store features
    store = FeatureStore()
    store.save_features(sample_feature_df, symbol="BTCUSDT", version="v1.0")

    # Train
    trainer = ModelTrainer("BTCUSDT", "v1.0", horizon=3)
    metrics = trainer.train()
    # Check that metrics exist and are floats
    assert "train_accuracy" in metrics
    assert "val_accuracy" in metrics
    # Artifacts should exist
    artifacts = ModelArtifacts("BTCUSDT", "v1.0")
    assert artifacts.model_dir.exists()
    assert (artifacts.model_dir / "model.pkl").exists()
    assert (artifacts.model_dir / "feature_names.json").exists()
    assert (artifacts.model_dir / "metadata.json").exists()

    cfg.data.parquet_dir = original_dir