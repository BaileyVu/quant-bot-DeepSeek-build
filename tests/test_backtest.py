from quantbot.backtest.engine import BacktestEngine
from quantbot.strategy.momentum import MomentumStrategy
from quantbot.backtest.datasets import synthetic_dataset
from quantbot.config import get_config


def test_backtest_metrics_snapshot():
    cfg = get_config(force_reload=True)
    data = synthetic_dataset(cfg.runtime.primary_symbol, cfg.runtime.bar_interval, periods=200)
    engine = BacktestEngine(config=cfg, strategy=MomentumStrategy(), data=data)
    result = engine.run()
    assert result.metrics["hit_rate"] >= 0
    assert len(result.equity_curve) > 0
