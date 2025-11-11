"""Configuration management for quantbot."""
from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime settings loaded from environment and .env."""

    exchange: Literal["binance", "hyperliquid"] = Field("binance", alias="EXCHANGE")
    mode: Literal["backtest", "paper", "live"] = Field("backtest", alias="MODE")
    symbol: str = Field("BTCUSDT", alias="SYMBOL")
    bar_interval: str = Field("1m", alias="BAR_INTERVAL")

    binance_api_key: Optional[str] = Field(default=None, alias="BINANCE_API_KEY")
    binance_api_secret: Optional[str] = Field(default=None, alias="BINANCE_API_SECRET")
    hyperliquid_pk: Optional[str] = Field(default=None, alias="HYPERLIQUID_PK")

    db_url: Optional[str] = Field(default=None, alias="DB_URL")

    maker_fee_bps: float = Field(0.02, alias="MAKER_FEE_BPS")
    taker_fee_bps: float = Field(0.05, alias="TAKER_FEE_BPS")

    max_leverage: float = Field(2.0, alias="MAX_LEVERAGE")
    max_notional: float = Field(100_000.0, alias="MAX_NOTIONAL")
    daily_loss_limit: float = Field(0.02, alias="DAILY_LOSS_LIMIT")

    funding_interval_minutes: int = Field(60 * 8, alias="FUNDING_INTERVAL_MINUTES")

    log_level: str = Field("INFO", alias="LOG_LEVEL")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("symbol")
    def _validate_symbol(cls, value: str, info):
        exchange = info.data.get("exchange", "binance")
        if exchange == "hyperliquid" and value.upper() == "BTCUSDT":
            return "BTC"
        return value.upper()

    @field_validator("db_url", mode="before")
    def _default_db_url(cls, value: Optional[str]) -> str:
        if value and str(value).strip():
            return value
        default_path = Path(os.getenv("QUANTBOT_DB", "./quantbot.db")).resolve()
        return f"sqlite:///{default_path}"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()  # type: ignore[call-arg]


__all__ = ["Settings", "get_settings"]
