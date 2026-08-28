"""Artifact storage for trained model and metadata."""

import pickle
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from quantos.config import get_config


class ModelArtifacts:
    """
    Save and load model artifacts locally.

    Artifacts are stored in: <data_dir>/models/<symbol>/<version>/
    """

    def __init__(self, symbol: str, version: str):
        self.config = get_config()
        self.symbol = symbol
        self.version = version
        base_dir = self.config.data.parquet_dir / "models" / symbol / version
        self.model_dir = base_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def save_model(self, model, feature_names: List[str], metadata: Dict[str, Any]) -> None:
        """
        Save the trained model, feature list, and metadata.

        Parameters
        ----------
        model : object
            Trained model (e.g., LightGBM classifier).
        feature_names : list
            Ordered list of feature names used during training.
        metadata : dict
            Additional metadata (split dates, metrics, params, etc.)
        """
        # Save model using pickle
        model_path = self.model_dir / "model.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model, f)
        logger.info(f"Saved model to {model_path}")

        # Save feature list
        feat_path = self.model_dir / "feature_names.json"
        with open(feat_path, "w") as f:
            json.dump(feature_names, f, indent=2)
        logger.info(f"Saved feature names to {feat_path}")

        # Save metadata
        meta_path = self.model_dir / "metadata.json"
        # Convert timestamps to strings
        metadata_copy = metadata.copy()
        for key in ["train_start", "train_end", "val_start", "val_end", "holdout_start", "holdout_end"]:
            if key in metadata_copy and metadata_copy[key] is not None:
                if isinstance(metadata_copy[key], datetime):
                    metadata_copy[key] = metadata_copy[key].isoformat()
        with open(meta_path, "w") as f:
            json.dump(metadata_copy, f, indent=2)
        logger.info(f"Saved metadata to {meta_path}")

        # Also save a summary file with human-readable info
        summary_path = self.model_dir / "summary.txt"
        with open(summary_path, "w") as f:
            f.write(f"Model trained for QuantOS V1\n")
            f.write(f"Symbol: {self.symbol}\n")
            f.write(f"Version: {self.version}\n")
            f.write(f"Horizon: {metadata.get('horizon')}\n")
            f.write(f"Training period: {metadata.get('train_start')} to {metadata.get('train_end')}\n")
            f.write(f"Validation period: {metadata.get('val_start')} to {metadata.get('val_end')}\n")
            f.write(f"Holdout period: {metadata.get('holdout_start')} to {metadata.get('holdout_end')}\n")
            f.write(f"Features used: {', '.join(feature_names)}\n")
            f.write(f"Metrics:\n")
            for k, v in metadata.get("metrics", {}).items():
                f.write(f"  {k}: {v:.4f}\n")
        logger.info(f"Saved summary to {summary_path}")

    def load_model(self):
        """Load the trained model and feature list."""
        model_path = self.model_dir / "model.pkl"
        feat_path = self.model_dir / "feature_names.json"
        meta_path = self.model_dir / "metadata.json"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found at {model_path}")
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        with open(feat_path, "r") as f:
            feature_names = json.load(f)
        with open(meta_path, "r") as f:
            metadata = json.load(f)
        return model, feature_names, metadata

    def list_artifacts(self) -> list:
        """List all available artifact files."""
        return [p.name for p in self.model_dir.iterdir() if p.is_file()]