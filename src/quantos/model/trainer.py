"""
Model training pipeline using LightGBM with fixed parameters.

No hyperparameter tuning – uses conservative defaults to reduce overfitting.
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, Optional
from datetime import datetime
import pickle
from pathlib import Path
import lightgbm as lgb
from sklearn.metrics import accuracy_score, roc_auc_score, log_loss
from loguru import logger

from quantos.config import get_config
from quantos.model.target import TargetCreator
from quantos.model.artifacts import ModelArtifacts
from quantos.feature_engine.storage import FeatureStore


class ModelTrainer:
    """
    Train a LightGBM classifier on feature data with chronological splitting.
    """

    def __init__(self, symbol: str, version: str = "v1.0", horizon: Optional[int] = None):
        self.config = get_config()
        self.symbol = symbol
        self.version = version
        self.horizon = horizon or self.config.model.target_horizon
        self.random_seed = self.config.model.random_seed
        self.train_ratio = self.config.model.train_split_ratio
        self.val_ratio = self.config.model.val_split_ratio
        # Model parameters – fixed, conservative
        self.model_params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "num_leaves": 31,          # small to avoid overfitting
            "max_depth": 6,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "min_child_samples": 20,
            "random_state": self.random_seed,
            "verbosity": -1,
        }
        self.feature_names = self.config.feature_engine.features  # from Milestone 2
        self.artifacts = ModelArtifacts(symbol, version)

    def load_data(self) -> pd.DataFrame:
        """Load features from FeatureStore."""
        store = FeatureStore()
        df = store.load_features(self.symbol, self.version)
        if df.empty:
            raise ValueError(f"No features found for {self.symbol} version {self.version}")
        # Ensure sorted by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)
        # Ensure required columns exist
        required = ["timestamp"] + self.feature_names
        missing = set(required) - set(df.columns)
        if missing:
            raise ValueError(f"Missing feature columns: {missing}")
        return df

    def split_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Chronological split: train -> validation -> holdout (future).
        """
        n = len(df)
        train_end = int(n * self.train_ratio)
        val_end = int(n * (self.train_ratio + self.val_ratio))
        train_df = df.iloc[:train_end].copy()
        val_df = df.iloc[train_end:val_end].copy()
        holdout_df = df.iloc[val_end:].copy()
        logger.info(f"Split: train {len(train_df)}, val {len(val_df)}, holdout {len(holdout_df)}")
        return train_df, val_df, holdout_df

    def prepare_features_target(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Extract features and target from a DataFrame.
        Drops rows where target is NaN (insufficient future data).
        """
        target_creator = TargetCreator(self.horizon)
        target = target_creator.create_target(df)
        # Features: use only the feature columns
        X = df[self.feature_names].copy()
        # Drop rows with NaN target
        valid_idx = target.notna()
        X = X.loc[valid_idx]
        y = target.loc[valid_idx]
        # Also drop rows with any NaN feature (if any)
        # LightGBM can handle NaN natively, but we keep simple: drop
        X_clean = X.dropna()
        y_clean = y.loc[X_clean.index]
        logger.info(f"Prepared {len(X_clean)} samples for training/evaluation.")
        return X_clean, y_clean

    def train(self) -> Dict[str, Any]:
        """
        Run the full training pipeline.
        Returns metrics and saves artifacts.
        """
        # 1. Load data
        df = self.load_data()

        # 2. Chronological split
        train_df, val_df, holdout_df = self.split_data(df)

        # 3. Prepare features/target for each split
        X_train, y_train = self.prepare_features_target(train_df)
        X_val, y_val = self.prepare_features_target(val_df)
        # Holdout is not used in training; we keep it isolated for later evaluation.

        if len(X_train) == 0 or len(X_val) == 0:
            raise ValueError("Insufficient data for training or validation after dropping NaNs.")

        # 4. Train model
        model = lgb.LGBMClassifier(**self.model_params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(20, verbose=False)],
        )

        # 5. Evaluate on train and val sets
        train_pred_prob = model.predict_proba(X_train)[:, 1]
        val_pred_prob = model.predict_proba(X_val)[:, 1]
        train_pred = (train_pred_prob >= 0.5).astype(int)
        val_pred = (val_pred_prob >= 0.5).astype(int)

        metrics = {
            "train_accuracy": accuracy_score(y_train, train_pred),
            "train_auc": roc_auc_score(y_train, train_pred_prob),
            "train_log_loss": log_loss(y_train, train_pred_prob),
            "val_accuracy": accuracy_score(y_val, val_pred),
            "val_auc": roc_auc_score(y_val, val_pred_prob),
            "val_log_loss": log_loss(y_val, val_pred_prob),
        }
        logger.info(f"Training metrics: {metrics}")

        # 6. Save artifacts
        artifacts_info = {
            "symbol": self.symbol,
            "version": self.version,
            "horizon": self.horizon,
            "train_start": train_df["timestamp"].min(),
            "train_end": train_df["timestamp"].max(),
            "val_start": val_df["timestamp"].min(),
            "val_end": val_df["timestamp"].max(),
            "holdout_start": holdout_df["timestamp"].min() if not holdout_df.empty else None,
            "holdout_end": holdout_df["timestamp"].max() if not holdout_df.empty else None,
            "feature_names": self.feature_names,
            "model_params": self.model_params,
            "metrics": metrics,
            "random_seed": self.random_seed,
            "n_train_samples": len(X_train),
            "n_val_samples": len(X_val),
        }
        self.artifacts.save_model(model, X_train.columns.tolist(), artifacts_info)

        return metrics
