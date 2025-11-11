"""Heartbeat utilities for live trading."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Awaitable, Callable


class Heartbeat:
    def __init__(self, interval: float = 5.0, timeout: float = 2.0) -> None:
        self.interval = interval
        self.timeout = timeout
        self._last: datetime | None = None

    def beat(self) -> None:
        self._last = datetime.utcnow()

    async def watch(self, callback: Callable[[], Awaitable[None]]) -> None:
        while True:
            await asyncio.sleep(self.interval)
            now = datetime.utcnow()
            if self._last and now - self._last > timedelta(seconds=self.timeout):
                await callback()


__all__ = ["Heartbeat"]
