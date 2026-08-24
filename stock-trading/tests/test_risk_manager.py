from autotrader.config import RiskConfig
from autotrader.portfolio.portfolio import Portfolio
from autotrader.risk.manager import RiskManager


def make_rm(**overrides):
    return RiskManager(RiskConfig(**overrides))


def test_stop_loss_triggers():
    rm = make_rm(stop_loss_pct=0.08)
    assert rm.check_exit("X", avg_cost=1000, price=915) is not None
    assert rm.check_exit("X", avg_cost=1000, price=950) is None


def test_take_profit_triggers():
    rm = make_rm(take_profit_pct=0.20)
    assert rm.check_exit("X", avg_cost=1000, price=1250) is not None
    assert rm.check_exit("X", avg_cost=1000, price=1100) is None


def test_size_buy_respects_position_limit():
    rm = make_rm(max_position_weight=0.20)
    p = Portfolio(cash=3_000_000)
    d = rm.size_buy(p, "X", price=2000, signal_score=1.0)
    assert d.approved
    # 最大でも資産の20% = 60万円 → 300株 (100株単位)
    assert d.quantity * 2000 <= 3_000_000 * 0.20 + 1e-6
    assert d.quantity % 100 == 0


def test_size_buy_rejects_when_already_full():
    rm = make_rm(max_position_weight=0.20)
    p = Portfolio(cash=3_000_000)
    p.apply_buy("2024-01-05", "X", 300, 2000, 0, "")
    d = rm.size_buy(p, "X", price=2000, signal_score=1.0)
    assert not d.approved


def test_size_buy_respects_gross_exposure():
    rm = make_rm(max_position_weight=0.5, max_gross_exposure=0.5)
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2024-01-05", "A", 400, 1000, 0, "")  # 40%投資済み
    d = rm.size_buy(p, "B", price=1000, signal_score=1.0)
    if d.approved:
        # 追加してもエクスポージャー50%以下
        assert (400_000 + d.quantity * 1000) / 1_000_000 <= 0.5 + 0.01


def test_size_buy_rejects_tiny_budget():
    rm = make_rm(max_position_weight=0.20)
    p = Portfolio(cash=50_000)  # 100株単位に届かない
    d = rm.size_buy(p, "X", price=2000, signal_score=1.0)
    assert not d.approved
