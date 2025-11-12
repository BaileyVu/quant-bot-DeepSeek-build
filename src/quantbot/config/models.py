"""Typed configuration models for quantbot."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RuntimeConfig(BaseModel):
    """Execution mode configuration."""

    mode: Literal["backtest", "paper", "live"] = "backtest"
    exchange: Literal["binance", "hyperliquid"] = "binance"
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])
    bar_interval: str = "1m"
    data_path: Path | None = None
    status_port: int = Field(9000, ge=1, le=65535)

    @field_validator("symbols", mode="before")
    @classmethod
    def _parse_symbols(cls, value: Iterable[str] | str) -> list[str]:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            if not parts:
                raise ValueError("symbols list cannot be empty")
            return [p.upper() for p in parts]
        seq = list(value)
        if not seq:
            raise ValueError("at least one symbol is required")
        return [str(item).upper() for item in seq]


class RiskConfig(BaseModel):
    """Risk guardrails."""

    max_daily_loss: float = Field(0.02, ge=0.0)
    max_drawdown: float = Field(0.3, ge=0.0)
    max_per_order_notional: float = Field(50_000.0, gt=0.0)
    max_leverage: float = Field(3.0, gt=0.0)
    max_open_positions: int = Field(10, ge=1)
    max_position_notional: float = Field(150_000.0, gt=0.0)
    kill_switch_file: Path | None = None
    allow_long: bool = True
    allow_short: bool = True
    max_spread_bps: float = Field(25.0, ge=0.0)
    max_price_jump_bps: float = Field(300.0, ge=0.0)
    max_data_lag_seconds: int = Field(120, ge=1)
    max_consecutive_errors: int = Field(5, ge=1)

    @model_validator(mode="after")
    def _validate_direction(self) -> "RiskConfig":
        if not (self.allow_long or self.allow_short):
            raise ValueError("at least one of allow_long/allow_short must be true")
        return self


class DataConfig(BaseModel):
    """Historical data configuration."""

    data_directory: Path = Field(default=Path("./data"))
    cache_directory: Path = Field(default=Path("./.cache"))
    database_url: str = Field(default="sqlite:///./quantbot.db")
    start: datetime | None = None
    end: datetime | None = None
    bar_aggregation: str = "1m"

    @field_validator("database_url", mode="before")
    @classmethod
    def _coerce_db_url(cls, value: str | Path | None) -> str:
        if value is None:
            return "sqlite:///./quantbot.db"
        if isinstance(value, Path):
            return f"sqlite:///{value.resolve()}"
        text = str(value)
        if text.startswith("sqlite://"):
            return text
        if "://" not in text:
            return f"sqlite:///{Path(text).resolve()}"
        return text

    @model_validator(mode="after")
    def _validate_range(self) -> "DataConfig":
        if self.start and self.end and self.start >= self.end:
            raise ValueError("data.start must be before data.end")
        return self


class ExchangeApiConfig(BaseModel):
    """API and credential configuration for an exchange."""

    rest_base: str
    ws_base: str | None = None
    timeout: float = Field(10.0, gt=0.0)
    rate_limit_per_minute: int = Field(1200, gt=0)
    api_key: str | None = Field(default=None, repr=False)
    api_secret: str | None = Field(default=None, repr=False)
    passphrase: str | None = Field(default=None, repr=False)
    account_id: str | None = None

    @field_validator("api_key", "api_secret", "passphrase")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def _default_exchange_configs() -> Dict[str, ExchangeApiConfig]:
    return {
        "binance": ExchangeApiConfig(
            rest_base="https://fapi.binance.com",
            ws_base="wss://fstream.binance.com/ws",
            timeout=10.0,
            rate_limit_per_minute=1200,
        ),
        "hyperliquid": ExchangeApiConfig(
            rest_base="https://api.hyperliquid.xyz",
            ws_base="wss://api.hyperliquid.xyz/ws",
            timeout=10.0,
            rate_limit_per_minute=600,
        ),
    }


class ApiConfig(BaseModel):
    """Top level API configuration keyed by exchange name."""

    exchanges: Dict[str, ExchangeApiConfig] = Field(default_factory=_default_exchange_configs)

    def for_exchange(self, name: str) -> ExchangeApiConfig:
        key = name.lower()
        try:
            return self.exchanges[key]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"no API configuration for exchange '{name}'") from exc


class ExecutionConfig(BaseModel):
    """Execution level configuration such as fees and slippage."""

    maker_fee_bps: float = Field(0.02, ge=0.0)
    taker_fee_bps: float = Field(0.05, ge=0.0)
    max_slippage_bps: float = Field(5.0, ge=0.0)
    funding_interval_minutes: int = Field(480, ge=1)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    structured: bool = True
    run_id: str | None = None


__all__ = [
    "RuntimeConfig",
    "RiskConfig",
    "DataConfig",
    "ApiConfig",
    "ExecutionConfig",
    "LoggingConfig",
    "ExchangeApiConfig",
]
