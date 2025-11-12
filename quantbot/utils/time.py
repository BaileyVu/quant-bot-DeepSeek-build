"""Time helpers for quantbot."""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""

    return datetime.now(tz=timezone.utc)


def to_unix_ms(dt: datetime) -> int:
    """Convert datetime to milliseconds since epoch."""

    return int(dt.timestamp() * 1000)


def from_unix_ms(value: int) -> datetime:
    """Convert milliseconds since epoch to datetime."""

    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


__all__ = ["utc_now", "to_unix_ms", "from_unix_ms"]
