"""Binance REST and WebSocket client."""

import requests
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode
import json
import time

from quantos.config import get_config
from quantos.logging import get_logger

logger = get_logger(__name__)

class BinanceClient:
    """Synchronous client for Binance public endpoints."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        config = get_config()
        self.base_url = base_url or config.binance.base_url
        self.timeout = timeout or config.binance.timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch klines from Binance.
        Returns raw kline data as list of lists.
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        data = self._get("/api/v3/klines", params)
        return data

    def ping(self) -> bool:
        """Test connectivity."""
        try:
            self._get("/api/v3/ping", {})
            return True
        except Exception:
            return False