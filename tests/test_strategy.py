from datetime import datetime

from quantbot.data import MarketState
from quantbot.strategy.momentum import MomentumStrategy, MomentumConfig


def make_state(price: float, prev: float) -> MarketState:
    return MarketState(
        symbol="BTCUSDT",
        time=datetime.utcnow(),
        bid=price - 5,
        ask=price + 5,
        mid=price,
        spread=10,
        last=price,
        realized_vol=0.001,
        returns=(price / prev) - 1,
        volume=1000.0,
    )


def test_momentum_target_direction():
    strategy = MomentumStrategy(MomentumConfig(fast=2, slow=4, z_clip=1.0, max_leverage=2.0))
    state1 = make_state(100, 100)
    target1 = strategy.on_bar(state1)
    assert target1.qty == 0
    state2 = make_state(101, 100)
    target2 = strategy.on_bar(state2)
    assert target2.qty >= 0
