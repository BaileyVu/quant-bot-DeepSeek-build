from quantbot.backtest.engine import BacktestEngine
from quantbot.strategy.momentum import MomentumStrategy
from quantbot.backtest.datasets import synthetic_dataset
from quantbot.config import get_settings


def test_backtest_metrics_snapshot():
    settings = get_settings()
    data = synthetic_dataset(settings.symbol, settings.bar_interval, periods=200)
    engine = BacktestEngine(settings=settings, strategy=MomentumStrategy(), data=data)
    result = engine.run()
    assert result.metrics["hit_rate"] >= 0
    assert len(result.equity_curve) > 0
