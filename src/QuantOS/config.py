"""Configuration loader using pydantic."""

from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field
import yaml
from dotenv import load_dotenv

load_dotenv()

class BinanceConfig(BaseModel):
    base_url: str = "https://api.binance.com"
    ws_url: str = "wss://stream.binance.com:9443/ws"
    timeout_seconds: int = 30

class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}"
    rotation: str = "1 day"
    retention: str = "1 month"

class DataConfig(BaseModel):
    parquet_dir: Path = Path("./data/parquet")
    live_buffer_size: int = 1000

class FeatureEngineConfig(BaseModel):
    feature_set_version: str = "v1.0"
    features: List[str] = Field(
        default_factory=lambda: [
            "return_1", "return_5", "return_10", "log_return_1",
            "volatility_10", "rsi_14", "macd_line", "macd_signal",
            "macd_histogram", "volume_ratio_10", "high_low_ratio",
            "close_position_10", "above_ma_20"
        ]
    )

class ModelConfig(BaseModel):
    target_horizon: int = 5  # minutes
    train_split_ratio: float = 0.7
    val_split_ratio: float = 0.15
    random_seed: int = 42

class BacktestConfig(BaseModel):
    fee_bps: float = 10.0          # fee in basis points (0.1% = 10 bps)
    slippage_bps: float = 5.0      # slippage in basis points (0.05% = 5 bps)
    initial_capital: float = 20.0  # USDT
    signal_threshold: float = 0.5  # probability threshold for entry
    long_only: bool = True         # only long positions
    walkforward_windows: int = 3   # number of walk‑forward test windows
    walkforward_train_ratio: float = 0.6   # proportion of data used for training in each window
    monte_carlo_iterations: int = 100
    monte_carlo_seed: int = 42

class PaperConfig(BaseModel):
    enabled: bool = True
    initial_capital: float = 20.0
    stale_data_timeout_seconds: int = 120
    persistence_dir: Path = Path("./data/paper")
    max_position_notional: float = 1000.0   # maximum notional per symbol
    max_daily_loss_pct: float = 10.0        # % of initial capital
    max_drawdown_pct: float = 20.0          # % of peak equity

class Config(BaseModel):
    symbols: List[str] = ["BTCUSDT", "ETHUSDT"]
    interval: str = "1m"
    initial_capital: float = 20.0
    binance: BinanceConfig = BinanceConfig()
    logging: LoggingConfig = LoggingConfig()
    data: DataConfig = DataConfig()
    feature_engine: FeatureEngineConfig = FeatureEngineConfig()
    model: ModelConfig = ModelConfig()
    backtest: BacktestConfig = BacktestConfig()
    paper: PaperConfig = PaperConfig()

    @classmethod
    def load(cls, path: Path = Path("config/config.yaml")) -> "Config":
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)

# Singleton for global access
_config: Optional[Config] = None

def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config