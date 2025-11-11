"""Structured logging utilities."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from .config import get_settings


class JsonFormatter(logging.Formatter):
    """Format logs as compact JSON."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "__dict__", {}).items():
            if key.startswith("_json_extras_"):
                payload.update(value)  # type: ignore[arg-type]
        return json.dumps(payload, separators=(",", ":"))


def configure_logging() -> None:
    """Configure root logger for the application."""

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]


def log_extra(**kwargs: Any) -> Dict[str, Any]:
    """Attach structured fields to a log record."""

    return {"_json_extras_log": kwargs}


__all__ = ["configure_logging", "log_extra"]
