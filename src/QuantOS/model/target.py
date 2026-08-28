"""Define the prediction target – future price direction."""

import pandas as pd
import numpy as np
from typing import Optional
from loguru import logger

from quantos.config import get_config


class TargetCreator:
    """
    Creates a binary classification target: 1 if price at t+horizon > price at t, else 0.

    The target is aligned with the feature timestamp (t) and uses only future data
    that would be known at the prediction horizon (t+horizon).
    """

    def __init__(self, horizon: Optional[int] = None):
        self.config = get_config()
        self.horizon = horizon or self.config.model.target_horizon
        if self.horizon <= 0:
            raise ValueError("Horizon must be positive integer.")

    def create_target(self, df: pd.DataFrame) -> pd.Series:
        """
        Compute target for each row in the DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain 'close' column, sorted by timestamp ascending.

        Returns
        -------
        pd.Series
            Binary target: 1 if close[ t+horizon ] > close[t], else 0.
            The last 'horizon' rows will have NaN because they lack sufficient future data.
        """
        if "close" not in df.columns:
            raise ValueError("DataFrame must contain 'close' column.")
        if len(df) < self.horizon + 1:
            logger.warning("Not enough data to compute target for the given horizon.")
            return pd.Series([np.nan] * len(df), index=df.index)

        # Shift forward to get future close
        future_close = df["close"].shift(-self.horizon)
        # Target: 1 if future close > current close
        target = (future_close > df["close"]).astype(float)
        # The last `horizon` rows will be NaN because future_close is NaN there
        return target