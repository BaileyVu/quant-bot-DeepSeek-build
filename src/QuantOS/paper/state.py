"""State persistence for paper runtime."""

import json
import pickle
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from loguru import logger

from quantos.config import get_config


class StatePersistence:
    def __init__(self):
        self.config = get_config().paper
        self.persistence_dir = self.config.persistence_dir
        self.persistence_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.persistence_dir / "paper_state.json"

    def save(self, state: Dict[str, Any]) -> None:
        """Save state to JSON."""
        # Convert datetime to string for JSON
        def convert(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Path):
                return str(obj)
            # Handle Trade objects? We'll store as dicts.
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return obj

        with open(self.state_file, "w") as f:
            json.dump(state, f, default=convert, indent=2)
        logger.info(f"State saved to {self.state_file}")

    def load(self) -> Dict[str, Any]:
        """Load state from JSON."""
        if not self.state_file.exists():
            return {}
        with open(self.state_file, "r") as f:
            data = json.load(f)
        # Convert timestamps back to datetime
        for trade in data.get("trades", []):
            if "entry_time" in trade:
                trade["entry_time"] = datetime.fromisoformat(trade["entry_time"])
            if "exit_time" in trade and trade["exit_time"]:
                trade["exit_time"] = datetime.fromisoformat(trade["exit_time"])
        return data