"""Settings object that binds together configuration sections."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import ApiConfig, DataConfig, ExecutionConfig, LoggingConfig, RiskConfig, RuntimeConfig


class Settings(BaseSettings):
    """Composite configuration loaded from environment, files and defaults."""

    environment: Literal["dev", "staging", "prod"] = Field(..., alias="ENVIRONMENT")
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        value = value.lower()
        if value not in {"dev", "staging", "prod"}:
            raise ValueError("ENVIRONMENT must be one of 'dev', 'staging', 'prod'")
        return value

    # Convenience properties for legacy call sites ---------------------------------
    @property
    def mode(self) -> Literal["backtest", "paper", "live"]:
        return self.runtime.mode

    @property
    def exchange(self) -> str:
        return self.runtime.exchange

    @property
    def symbols(self) -> list[str]:
        return self.runtime.symbols

    @property
    def symbol(self) -> str:
        return self.runtime.symbols[0]

    @property
    def bar_interval(self) -> str:
        return self.runtime.bar_interval

    @property
    def maker_fee_bps(self) -> float:
        return self.execution.maker_fee_bps

    @property
    def taker_fee_bps(self) -> float:
        return self.execution.taker_fee_bps

    @property
    def max_leverage(self) -> float:
        return self.risk.max_leverage

    @property
    def max_notional(self) -> float:
        return self.risk.max_position_notional

    @property
    def daily_loss_limit(self) -> float:
        return self.risk.max_daily_loss

    @property
    def db_url(self) -> str:
        return self.data.database_url

    def api_for_exchange(self, name: str):
        return self.api.for_exchange(name)

    def logging_metadata(self) -> dict[str, str]:
        return {
            "env": self.environment,
            "mode": self.runtime.mode,
            "exchange": self.runtime.exchange,
            "symbols": ",".join(self.runtime.symbols),
        }


_DEFAULT_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Return process-wide cached settings."""

    global _DEFAULT_SETTINGS
    if _DEFAULT_SETTINGS is None:
        _DEFAULT_SETTINGS = Settings()
    return _DEFAULT_SETTINGS


def reset_settings_cache() -> None:
    global _DEFAULT_SETTINGS
    _DEFAULT_SETTINGS = None


__all__ = ["Settings", "get_settings", "reset_settings_cache"]
