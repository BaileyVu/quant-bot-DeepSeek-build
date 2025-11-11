"""Funding PnL modelling."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FundingEvent:
    timestamp: datetime
    rate: float


def funding_payment(notional: float, rate: float) -> float:
    """Return funding payment (positive = received)."""

    return notional * rate


class FundingModel:
    def __init__(self, interval_minutes: int) -> None:
        self.interval = timedelta(minutes=interval_minutes)
        self._last_event: datetime | None = None

    def should_apply(self, now: datetime) -> bool:
        if self._last_event is None:
            return True
        return now - self._last_event >= self.interval

    def apply(self, now: datetime, notional: float, rate: float) -> float:
        if not self.should_apply(now):
            return 0.0
        self._last_event = now
        return funding_payment(notional, rate)


__all__ = ["FundingModel", "funding_payment", "FundingEvent"]
