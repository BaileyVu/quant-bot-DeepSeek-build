from datetime import datetime, timezone

from quantbot.config import load_settings
from quantbot.data.normalizer import MarketState
from quantbot.exchange.models import AccountState, OrderRequest, Position, SymbolMeta
from quantbot.risk.limits import LimitChecker
from quantbot.risk.manager import RiskManager
from quantbot.risk.stops import StopManager


def test_daily_kill_switch_triggers():
    manager = StopManager(10_000.0)
    assert manager.check_daily(9_900.0)
    assert not manager.check_daily(9_000.0)


def test_leverage_limit():
    checker = LimitChecker(equity=10_000.0)
    result = checker.check_leverage(40_000.0)
    assert not result.allowed


def test_risk_manager_blocks_large_order():
    settings = load_settings(use_cache=False)
    risk_manager = RiskManager(settings)
    now = datetime.now(timezone.utc)
    state = MarketState(
        symbol=settings.symbol,
        time=now,
        bid=100.0,
        ask=100.2,
        mid=100.1,
        spread=0.2,
        last=100.0,
        realized_vol=0.001,
        returns=0.0,
    )
    account = AccountState(equity=10_000.0, available_balance=10_000.0, timestamp=now)
    positions: dict[str, Position] = {}
    symbol_meta = SymbolMeta(
        symbol=settings.symbol,
        price_precision=2,
        size_precision=3,
        tick_size=0.1,
        step_size=0.001,
        min_notional=5.0,
        max_leverage=settings.risk.max_leverage,
    )
    request = OrderRequest(symbol=settings.symbol, side="buy", type="market", qty=1_000.0, price=None)
    decision = risk_manager.validate_order(request, account, positions, state, symbol_meta)
    assert not decision.allowed
