"""Structured logging utilities."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from .config import get_settings
from .utils.time import utc_now


class JsonFormatter(logging.Formatter):
    """Format logs as compact JSON."""

    def __init__(self, base_fields: Mapping[str, Any] | None = None) -> None:
        super().__init__()
        self.base_fields = dict(base_fields or {})

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            **self.base_fields,
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


def configure_logging(run_id: str | None = None) -> str:
    """Configure root logger for the application."""

    settings = get_settings()
    metadata = settings.logging_metadata()
    resolved_run_id = run_id or settings.logging.run_id or utc_now().strftime("%Y%m%d-%H%M%S")
    metadata["run_id"] = resolved_run_id
    level = getattr(logging, settings.logging.level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.logging.structured:
        handler.setFormatter(JsonFormatter(metadata))
    else:  # pragma: no cover - optional plain logs
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    return resolved_run_id


def log_extra(**kwargs: Any) -> Dict[str, Any]:
    """Attach structured fields to a log record."""

    return {"_json_extras_log": kwargs}


__all__ = ["configure_logging", "log_extra"]
