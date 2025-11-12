"""Simple in-process metrics registry."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from statistics import mean
from typing import Deque, Dict, List


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._latencies: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=256))
        self._gauges: Dict[str, float] = {}

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe_latency(self, name: str, value: float) -> None:
        with self._lock:
            self._latencies[name].append(value)

    def snapshot(self) -> dict:
        with self._lock:
            latencies = {
                key: {
                    "avg_ms": mean(values) if values else 0.0,
                    "p95_ms": sorted(values)[int(0.95 * (len(values) - 1))] if values else 0.0,
                    "count": len(values),
                }
                for key, values in self._latencies.items()
            }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "latencies": latencies,
                "timestamp": time.time(),
            }


metrics = MetricsRegistry()

__all__ = ["metrics", "MetricsRegistry"]
