from quantbot.risk.stops import StopManager
from quantbot.risk.limits import LimitChecker


def test_daily_kill_switch_triggers():
    manager = StopManager(10_000.0)
    assert manager.check_daily(9_900.0)
    assert not manager.check_daily(9_000.0)


def test_leverage_limit():
    checker = LimitChecker(equity=10_000.0)
    result = checker.check_leverage(30_000.0)
    assert not result.allowed
