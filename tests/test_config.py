import pytest

from quantbot.config import ConfigError, load_settings, reset_settings_cache


def test_invalid_environment_rejected(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "qa")
    reset_settings_cache()
    with pytest.raises(ConfigError):
        load_settings(use_cache=False)
    monkeypatch.setenv("ENVIRONMENT", "dev")
    reset_settings_cache()
    settings = load_settings(use_cache=False)
    assert settings.environment == "dev"
