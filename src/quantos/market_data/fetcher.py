"""High-level fetcher that combines Binance client, normalization, validation, storage."""

from datetime import datetime, timedelta
from typing import List, Optional
from quantos.adapters.binance import BinanceClient
from quantos.market_data.validator import normalize_binance_kline, validate_candle, detect_duplicates
from quantos.infrastructure.persistence import ParquetStore
from quantos.logging import get_logger

logger = get_logger(__name__)

class MarketDataFetcher:
    def __init__(self):
        self.client = BinanceClient()
        self.store = ParquetStore()

    def fetch_historical(
        self,
        symbol: str,
        interval: str = "1m",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """Fetch raw klines, normalize, validate, and store."""
        all_candles = []
        current_start = start_time
        while True:
            raw = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=end_time,
                limit=limit,
            )
            if not raw:
                break
            candles = [normalize_binance_kline(k, symbol, interval) for k in raw]
            valid = [c for c in candles if validate_candle(c)]
            if not valid:
                break
            unique = detect_duplicates(valid)
            all_candles.extend(unique)
            if len(raw) < limit:
                break
            last_ts = valid[-1].timestamp
            current_start = last_ts + timedelta(minutes=1)
            if end_time and current_start > end_time:
                break
        if all_candles:
            self.store.append_candles(all_candles)
            logger.info(f"Fetched and stored {len(all_candles)} candles for {symbol}")
        return all_candles