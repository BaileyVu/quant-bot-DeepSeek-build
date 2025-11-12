"""Configuration loader utilities."""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from pydantic import ValidationError

from .models import ApiConfig, DataConfig, ExecutionConfig, LoggingConfig, RiskConfig, RuntimeConfig
from .settings import Settings


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded."""


def _deep_update(base: MutableMapping[str, Any], overrides: Mapping[str, Any]) -> MutableMapping[str, Any]:
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            _deep_update(base[key], value)  # type: ignore[arg-type]
        else:
            base[key] = value
    return base


def load_config_file(path: Path) -> dict[str, Any]:
    try:
        with path.expanduser().resolve().open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"config file '{path}' not found") from exc


def _base_defaults() -> dict[str, Any]:
    return {
        "runtime": RuntimeConfig().model_dump(),
        "risk": RiskConfig().model_dump(),
        "data": DataConfig().model_dump(),
        "api": ApiConfig().model_dump(),
        "execution": ExecutionConfig().model_dump(),
        "logging": LoggingConfig().model_dump(),
    }


def load_settings(
    config_path: str | os.PathLike[str] | None = None,
    overrides: Mapping[str, Any] | None = None,
    use_cache: bool = True,
) -> Settings:
    """Load :class:`Settings` from file/environment."""

    path = Path(config_path) if config_path else None

    @lru_cache(maxsize=8)
    def _load_cached(resolved: Path | None) -> Settings:
        payload: dict[str, Any] = _base_defaults()
        if resolved:
            payload = _deep_update(payload, load_config_file(resolved))
        try:
            return Settings(**payload)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

    settings = _load_cached(path.resolve() if path else None) if use_cache else None
    if settings is None:
        payload = _base_defaults()
        if path:
            payload = _deep_update(payload, load_config_file(path.resolve()))
        try:
            settings = Settings(**payload)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc

    if overrides:
        settings = settings.model_copy(update=overrides)
    return settings


__all__ = ["load_settings", "ConfigError", "load_config_file"]
