"""
Deterministic, causal feature computation from OHLCV candles.

All features are computed using only information available at timestamp t.
No lookahead, no centered windows, no future data.
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from datetime import datetime
from loguru import logger

from quantos.config import get_config
from quantos.domain.feature import FeatureVector


class FeatureEngine:
    """
    Computes a compact set of features for a given symbol and date range.

    The feature set is fixed and small (13 features) to reduce overfitting
    and maintain clarity.
    """

    def __init__(self, version: str = "v1.0"):
        self.version = version
        self.config = get_config()
        self.feature_names = self.config.feature_engine.features

    def compute_features(
        self, df_candles: pd.DataFrame, symbol: str
    ) -> pd.DataFrame:
        """
        Compute features from a DataFrame of OHLCV candles.

        Parameters
        ----------
        df_candles : pd.DataFrame
            Must contain columns: timestamp, open, high, low, close, volume.
            Timestamps must be sorted ascending and be unique.
        symbol : str
            Symbol for which features are computed (e.g., "BTCUSDT").

        Returns
        -------
        pd.DataFrame
            A DataFrame with columns:
                timestamp, symbol, version, and each feature.
            One row per input candle (first few rows may have NaN features
            due to insufficient history).
        """
        if df_candles.empty:
            return pd.DataFrame()

        required = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = set(required) - set(df_candles.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        df = df_candles.sort_values("timestamp").reset_index(drop=True)
        if df["timestamp"].duplicated().any():
            raise ValueError("Duplicate timestamps found; remove them before feature computation.")

        price_cols = ["open", "high", "low", "close"]
        df[price_cols] = df[price_cols].astype(float)
        df["volume"] = df["volume"].astype(float)

        df["return_1"] = df["close"].pct_change(periods=1)
        df["return_5"] = df["close"].pct_change(periods=5)
        df["return_10"] = df["close"].pct_change(periods=10)
        df["log_return_1"] = np.log(df["close"] / df["close"].shift(1))

        df["volatility_10"] = df["return_1"].rolling(window=10).std()

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi_14"] = 100 - (100 / (1 + rs))

        exp1 = df["close"].ewm(span=12, adjust=False).mean()
        exp2 = df["close"].ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal = macd_line.ewm(span=9, adjust=False).mean()
        df["macd_line"] = macd_line
        df["macd_signal"] = signal
        df["macd_histogram"] = macd_line - signal

        vol_ma10 = df["volume"].rolling(window=10).mean()
        df["volume_ratio_10"] = df["volume"] / vol_ma10

        df["high_low_ratio"] = (df["high"] - df["low"]) / df["close"]

        high_10 = df["high"].rolling(window=10).max()
        low_10 = df["low"].rolling(window=10).min()
        df["close_position_10"] = (df["close"] - low_10) / (high_10 - low_10)

        ma20 = df["close"].rolling(window=20).mean()
        df["above_ma_20"] = (df["close"] > ma20).astype(float)

        available = set(df.columns)
        missing_features = set(self.feature_names) - available
        if missing_features:
            raise ValueError(f"Missing computed features: {missing_features}")

        out_df = df[["timestamp"]].copy()
        out_df["symbol"] = symbol
        out_df["version"] = self.version
        for feat in self.feature_names:
            out_df[feat] = df[feat]

        return out_df

    def compute_feature_vectors(
        self, df_candles: pd.DataFrame, symbol: str
    ) -> List[FeatureVector]:
        df_feat = self.compute_features(df_candles, symbol)
        vectors = []
        for _, row in df_feat.iterrows():
            feat_dict = {f: row[f] for f in self.feature_names if not pd.isna(row[f])}
            vectors.append(
                FeatureVector(
                    symbol=row["symbol"],
                    timestamp=row["timestamp"].to_pydatetime(),
                    version=row["version"],
                    features=feat_dict,
                )
            )
        return vectors