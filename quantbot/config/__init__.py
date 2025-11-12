"""Configuration management for the trading system."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .models import (
    ApiConfig,
    AppConfig,
    DataConfig,
    FeeConfig,
    LoggingConfig,
    StorageConfig,
    RuntimeConfig,
    RiskConfig,
    deep_update,
    load_app_config,
)

_CONFIG: AppConfig | None = None


def get_config(
    *,
    config_path: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    force_reload: bool = False,
) -> AppConfig:
    """Return the cached application configuration."""

    global _CONFIG
    if force_reload or _CONFIG is None or config_path or overrides:
        _CONFIG = load_app_config(config_path=config_path, overrides=overrides)
    return _CONFIG


def get_settings(**kwargs: Any) -> AppConfig:
    """Backward compatible alias used by existing modules."""

    return get_config(**kwargs)


__all__ = [
    "AppConfig",
    "RuntimeConfig",
    "RiskConfig",
    "DataConfig",
    "ApiConfig",
    "FeeConfig",
    "LoggingConfig",
    "StorageConfig",
    "get_config",
    "get_settings",
    "deep_update",
]
