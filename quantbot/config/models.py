"""Typed configuration models for the trading system."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, MutableMapping, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    PositiveFloat,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "staging", "prod"]
Mode = Literal["backtest", "paper", "live"]
Exchange = Literal["binance", "hyperliquid"]


def _expand_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    return path


class RuntimeConfig(BaseModel):
    """Runtime execution parameters."""

    mode: Mode = Field(default="backtest", validation_alias=AliasChoices("mode", "MODE"))
    exchange: Exchange = Field(default="binance", validation_alias=AliasChoices("exchange", "EXCHANGE"))
    primary_symbol: str = Field(
        default="BTCUSDT",
        validation_alias=AliasChoices("primary_symbol", "symbol", "SYMBOL"),
    )
    symbols: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("symbols", "SYMBOLS"),
    )
    bar_interval: str = Field(
        default="1m",
        validation_alias=AliasChoices("bar_interval", "BAR_INTERVAL"),
    )
    data_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("data_path", "DATA_PATH"),
    )
    funding_interval_minutes: int = Field(
        default=8 * 60,
        ge=1,
        validation_alias=AliasChoices("funding_interval_minutes", "FUNDING_INTERVAL_MINUTES"),
    )
    run_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("run_id", "RUN_ID"),
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def _split_symbols(cls, value: Any) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [token.strip().upper() for token in value.split(",") if token.strip()]
        if isinstance(value, Iterable):
            return [str(token).upper() for token in value]
        raise TypeError("symbols must be iterable or comma separated string")

    @field_validator("primary_symbol")
    @classmethod
    def _upper_primary(cls, value: str) -> str:
        return value.upper()

    @field_validator("data_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Path | None:
        if value in (None, ""):
            return None
        return _expand_path(value)

    @model_validator(mode="after")
    def _ensure_symbol_in_list(self) -> "RuntimeConfig":
        primary = self.primary_symbol
        if primary not in self.symbols:
            self.symbols.insert(0, primary)
        return self


class RiskConfig(BaseModel):
    """Global and per-symbol risk limits."""

    max_daily_loss: PositiveFloat = Field(
        default=0.02,
        validation_alias=AliasChoices("max_daily_loss", "DAILY_LOSS_LIMIT"),
        description="Fractional daily loss limit that will halt trading when breached.",
    )
    max_drawdown: PositiveFloat = Field(
        default=0.2,
        validation_alias=AliasChoices("max_drawdown", "MAX_DRAWDOWN"),
    )
    max_order_notional: PositiveFloat = Field(
        default=100_000.0,
        validation_alias=AliasChoices("max_order_notional", "MAX_NOTIONAL"),
    )
    max_leverage: PositiveFloat = Field(
        default=2.0,
        validation_alias=AliasChoices("max_leverage", "MAX_LEVERAGE"),
    )
    max_open_positions: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices("max_open_positions", "MAX_OPEN_POSITIONS"),
    )
    per_symbol_notional: dict[str, PositiveFloat] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("per_symbol_notional", "PER_SYMBOL_NOTIONAL"),
    )
    long_only: bool = Field(
        default=False,
        validation_alias=AliasChoices("long_only", "LONG_ONLY"),
    )
    short_only: bool = Field(
        default=False,
        validation_alias=AliasChoices("short_only", "SHORT_ONLY"),
    )

    @field_validator("per_symbol_notional", mode="before")
    @classmethod
    def _decode_per_symbol(cls, value: Any) -> dict[str, PositiveFloat]:
        if value in (None, "", {}):
            return {}
        if isinstance(value, Mapping):
            return {str(k).upper(): float(v) for k, v in value.items()}
        if isinstance(value, str):
            out: dict[str, PositiveFloat] = {}
            for token in value.split(","):
                if ":" not in token:
                    continue
                symbol, amount = token.split(":", 1)
                out[symbol.strip().upper()] = float(amount)
            return out
        raise TypeError("per_symbol_notional must be mapping or string")

    @model_validator(mode="after")
    def _validate_direction(self) -> "RiskConfig":
        if self.long_only and self.short_only:
            raise ValueError("long_only and short_only cannot both be enabled")
        return self


class DataConfig(BaseModel):
    """Historical data inputs."""

    data_dir: Path = Field(default=Path("./data"), validation_alias=AliasChoices("data_dir", "DATA_DIR"))
    start: Optional[str] = Field(default=None, validation_alias=AliasChoices("start", "DATA_START"))
    end: Optional[str] = Field(default=None, validation_alias=AliasChoices("end", "DATA_END"))
    aggregation: str = Field(default="1m", validation_alias=AliasChoices("aggregation", "DATA_AGGREGATION"))
    preload_days: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("preload_days", "DATA_PRELOAD_DAYS"),
    )

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_dir(cls, value: Any) -> Path:
        if value in (None, ""):
            value = Path("./data")
        return _expand_path(value) or Path("./data").resolve()


class RateLimitConfig(BaseModel):
    requests_per_minute: int = Field(default=600, ge=1)
    burst: int = Field(default=100, ge=1)


class ApiConfig(BaseModel):
    """Exchange connectivity configuration."""

    request_timeout: PositiveFloat = Field(
        default=5.0,
        validation_alias=AliasChoices("request_timeout", "REQUEST_TIMEOUT"),
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        validation_alias=AliasChoices("max_retries", "MAX_RETRIES"),
    )
    retry_backoff_seconds: PositiveFloat = Field(
        default=0.5,
        validation_alias=AliasChoices("retry_backoff_seconds", "RETRY_BACKOFF_SECONDS"),
    )
    binance_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("binance_api_key", "BINANCE_API_KEY"),
    )
    binance_api_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("binance_api_secret", "BINANCE_API_SECRET"),
    )
    hyperliquid_private_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("hyperliquid_private_key", "HYPERLIQUID_PK"),
    )
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    http_proxy: str | None = Field(
        default=None,
        validation_alias=AliasChoices("http_proxy", "HTTP_PROXY"),
    )


class StorageConfig(BaseModel):
    """Database connection details."""

    url: str = Field(default="sqlite:///quantbot.db", validation_alias=AliasChoices("url", "DB_URL"))

    @field_validator("url", mode="before")
    @classmethod
    def _default_url(cls, value: Any) -> str:
        if value in (None, ""):
            default_path = Path(os.getenv("QUANTBOT_DB", "./quantbot.db")).expanduser().resolve()
            return f"sqlite:///{default_path}"
        return str(value)


class FeeConfig(BaseModel):
    maker_bps: PositiveFloat = Field(default=0.02, validation_alias=AliasChoices("maker_bps", "MAKER_FEE_BPS"))
    taker_bps: PositiveFloat = Field(default=0.05, validation_alias=AliasChoices("taker_bps", "TAKER_FEE_BPS"))

    @property
    def maker_rate(self) -> float:
        return self.maker_bps / 10_000.0

    @property
    def taker_rate(self) -> float:
        return self.taker_bps / 10_000.0


class LoggingConfig(BaseModel):
    level: str = Field(default="INFO", validation_alias=AliasChoices("level", "LOG_LEVEL"))
    run_id: str | None = Field(default=None, validation_alias=AliasChoices("run_id", "LOG_RUN_ID"))


class AppConfig(BaseSettings):
    """Top-level typed application configuration."""

    environment: Environment = Field(validation_alias=AliasChoices("environment", "ENVIRONMENT"))
    runtime: RuntimeConfig = RuntimeConfig()
    risk: RiskConfig = RiskConfig()
    data: DataConfig = DataConfig()
    api: ApiConfig = ApiConfig()
    fees: FeeConfig = FeeConfig()
    logging: LoggingConfig = LoggingConfig()
    storage: StorageConfig = StorageConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _validate_environment(self) -> "AppConfig":
        if self.environment not in ("dev", "staging", "prod"):
            raise ValueError("ENVIRONMENT must be one of dev|staging|prod")
        return self

    @property
    def maker_fee_bps(self) -> float:
        return self.fees.maker_bps

    @property
    def taker_fee_bps(self) -> float:
        return self.fees.taker_bps


def deep_update(base: MutableMapping[str, Any], updates: Mapping[str, Any]) -> MutableMapping[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            deep_update(base[key], value)  # type: ignore[index]
        else:
            base[key] = value  # type: ignore[index]
    return base


def load_app_config(
    *,
    config_path: Path | str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> AppConfig:
    data: dict[str, Any] = {}
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"config file {path} does not exist")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    if overrides:
        data = deep_update(data, dict(overrides))
    try:
        return AppConfig(**data)
    except ValidationError as exc:  # pragma: no cover - configuration errors should surface early
        raise RuntimeError(f"configuration validation failed: {exc}") from exc


__all__ = [
    "AppConfig",
    "RuntimeConfig",
    "RiskConfig",
    "DataConfig",
    "ApiConfig",
    "FeeConfig",
    "LoggingConfig",
    "StorageConfig",
    "load_app_config",
    "deep_update",
]
