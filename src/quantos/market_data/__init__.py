"""Market data handling (historical and live)."""
from .fetcher import MarketDataFetcher
from .live import LiveMarketData
from .validator import validate_candle, normalize_binance_kline, detect_duplicates, detect_missing_candles