"""Structured logging utilities."""
from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from .config import AppConfig, get_config

_BASE_FIELDS: Dict[str, Any] = {}


class JsonFormatter(logging.Formatter):
    """Format logs as compact JSON with contextual metadata."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            **_BASE_FIELDS,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extras = getattr(record, "_json_extras", None)
        if isinstance(extras, dict):
            payload.update(extras)
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(config: AppConfig | None = None) -> AppConfig:
    """Configure root logger for the application."""

    cfg = config or get_config()
    run_id = cfg.logging.run_id or cfg.runtime.run_id or uuid.uuid4().hex[:12]
    _BASE_FIELDS.update(
        {
            "env": cfg.environment,
            "mode": cfg.runtime.mode,
            "exchange": cfg.runtime.exchange,
            "symbols": ",".join(cfg.runtime.symbols),
            "run_id": run_id,
        }
    )
    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    logging.getLogger("quantbot").debug("logging configured", extra=log_extra(run_id=run_id))
    return cfg


def log_extra(**kwargs: Any) -> Dict[str, Any]:
    """Attach structured fields to a log record."""

    payload = dict(kwargs)
    return {"_json_extras": payload}


__all__ = ["configure_logging", "log_extra"]
