import os

import pytest

from quantbot.config.models import load_app_config


def test_environment_validation():
    with pytest.raises(RuntimeError):
        load_app_config(overrides={"environment": "qa"})


def test_nested_overrides(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
        environment = "dev"
        [runtime]
        mode = "backtest"
        exchange = "binance"
        primary_symbol = "ETHUSDT"
        """
    )
    cfg = load_app_config(config_path=config_path)
    assert cfg.runtime.primary_symbol == "ETHUSDT"
    assert cfg.environment == "dev"
