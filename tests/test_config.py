import pytest
from quantos.config import Config

def test_config_load(test_config_path):
    cfg = Config.load(test_config_path)
    assert cfg.symbols == ["BTCUSDT"]
    assert cfg.interval == "1m"
    assert cfg.logging.level == "DEBUG"