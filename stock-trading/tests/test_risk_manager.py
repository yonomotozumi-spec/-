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


def test_size_buy_fractional_lot_allows_small_budget():
    # 単元未満株 (lot_size=1) なら資金50万でも高価格銘柄を買える
    rm = make_rm(max_position_weight=0.25)
    p = Portfolio(cash=500_000)
    d = rm.size_buy(p, "X", price=13_000, signal_score=1.0, lot_size=1)
    assert d.approved
    assert 1 <= d.quantity * 13_000 <= 500_000 * 0.25 + 13_000


# ---- トレーリングストップ ----------------------------------------------
def test_trailing_stop_locks_in_profit():
    """高値から12%下落で利確。取得価格より上でのみ作動する"""
    rm = make_rm(take_profit_pct=0.0, trailing_stop_pct=0.12)
    # 取得1000 → 高値1500 → トレーリング線は1320
    assert rm.check_exit("X", 1000, 1400, peak_price=1500) is None      # まだ上
    r = rm.check_exit("X", 1000, 1300, peak_price=1500)                 # 線を割った
    assert r is not None and "トレーリング利確" in r


def test_trailing_stop_does_not_fire_below_cost():
    """含み損の領域では作動せず、損切りに委ねる"""
    rm = make_rm(stop_loss_pct=0.08, take_profit_pct=0.0, trailing_stop_pct=0.12)
    # 取得1000 → 高値1050 → トレーリング線924 は取得価格未満なので発動しない
    assert rm.check_exit("X", 1000, 930, peak_price=1050) is None
    # -8%に達すれば損切りが働く
    assert "損切り" in rm.check_exit("X", 1000, 915, peak_price=1050)


def test_take_profit_disabled_when_zero():
    """take_profit_pct=0 なら上値を制限しない"""
    rm = make_rm(take_profit_pct=0.0)
    assert rm.check_exit("X", 1000, 3000) is None   # +200%でも利確しない


def test_stop_loss_takes_precedence_over_trailing():
    rm = make_rm(stop_loss_pct=0.08, trailing_stop_pct=0.05)
    assert "損切り" in rm.check_exit("X", 1000, 900, peak_price=1010)
