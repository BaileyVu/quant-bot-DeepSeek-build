import pytest
from quantos.market_data.fetcher import MarketDataFetcher
from datetime import datetime, timedelta

@pytest.mark.integration
def test_fetch_historical_live():
    fetcher = MarketDataFetcher()
    end = datetime.utcnow()
    start = end - timedelta(days=1)
    candles = fetcher.fetch_historical("BTCUSDT", "1m", start, end)
    assert len(candles) > 0