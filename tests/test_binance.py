import pytest
from unittest.mock import patch, MagicMock
from quantos.adapters.binance import BinanceClient

@patch("quantos.adapters.binance.requests.Session.get")
def test_binance_get_klines(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [[
        1704067200000, "100.0", "101.0", "99.0", "100.5", "10.0",
        1704067260000, "0", "0", "0", "0", "0", "0"
    ]]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    client = BinanceClient(base_url="https://test")
    data = client.get_klines("BTCUSDT", "1m")
    assert len(data) == 1
    assert data[0][1] == "100.0"