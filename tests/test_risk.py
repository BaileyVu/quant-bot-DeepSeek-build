from datetime import datetime, timedelta, timezone

from quantbot.config import get_config
from quantbot.core import OrderRequest
from quantbot.data import MarketState
from quantbot.exchange import AccountState
from quantbot.risk.stops import StopManager
from quantbot.risk.limits import LimitChecker
from quantbot.risk.manager import RiskManager


def test_daily_kill_switch_triggers():
    manager = StopManager(10_000.0)
    assert manager.check_daily(9_900.0)
    assert not manager.check_daily(9_000.0)


def test_leverage_limit():
    checker = LimitChecker(equity=10_000.0)
    result = checker.check_leverage(30_000.0)
    assert not result.allowed


def _make_state(price: float = 100.0) -> MarketState:
    return MarketState(
        symbol="BTCUSDT",
        time=datetime.now(tz=timezone.utc),
        bid=price - 0.5,
        ask=price + 0.5,
        mid=price,
        spread=1.0,
        last=price,
        realized_vol=0.001,
        returns=0.0,
        volume=1000.0,
    )


def test_risk_manager_leverage_rejection():
    cfg = get_config(force_reload=True)
    risk = RiskManager(cfg, max_data_lag=timedelta(minutes=5))
    state = _make_state()
    account = AccountState(
        equity=1_000.0,
        available_margin=1_000.0,
        total_margin=1_000.0,
        timestamp=state.time,
    )
    request = OrderRequest(symbol="BTCUSDT", side="buy", quantity=20.0, order_type="market", price=state.mid)
    decision = risk.validate_order(request, state, account, {})
    assert not decision.allowed


def test_risk_manager_kill_switch_on_drawdown():
    cfg = get_config(force_reload=True)
    risk = RiskManager(cfg)
    today = datetime.now(tz=timezone.utc).date()
    risk.state.day = today
    risk.state.start_equity = 10_000.0
    risk.state.peak_equity = 10_000.0
    risk.on_pnl_update(9_000.0)
    assert risk.state.kill_triggered
    assert not risk.is_trading_allowed()
