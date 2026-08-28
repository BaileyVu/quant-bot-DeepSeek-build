"""Live market data via WebSocket."""

import json
import threading
import time
from datetime import datetime
from typing import Callable, Optional
from decimal import Decimal

import websocket

from quantos.config import get_config
from quantos.logging import get_logger
from quantos.domain.candle import Candle
from quantos.market_data.validator import validate_candle, normalize_binance_kline

logger = get_logger(__name__)

class LiveMarketData:
    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1m"):
        self.symbol = symbol
        self.interval = interval
        self.config = get_config()
        self.ws_url = self.config.binance.ws_url
        self.ws = None
        self.callbacks: list[Callable[[Candle], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def on_candle(self, callback: Callable[[Candle], None]):
        self.callbacks.append(callback)

    def start(self):
        """Start WebSocket connection in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

    def _run(self):
        stream_name = f"{self.symbol.lower()}@kline_{self.interval}"
        url = f"{self.ws_url}/{stream_name}"
        logger.info(f"Connecting to WebSocket: {url}")
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )
        self.ws.run_forever()

    def _on_open(self, ws):
        logger.info("WebSocket connected")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket closed")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            kline = data.get("k")
            if not kline:
                return
            if not kline.get("x"):
                return
            raw = [
                kline["t"],
                kline["o"],
                kline["h"],
                kline["l"],
                kline["c"],
                kline["v"],
                kline["T"],
            ]
            candle = normalize_binance_kline(raw, self.symbol, self.interval)
            if validate_candle(candle):
                logger.debug(f"Received completed candle: {candle.timestamp}")
                for cb in self.callbacks:
                    cb(candle)
            else:
                logger.warning(f"Invalid live candle: {candle}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")