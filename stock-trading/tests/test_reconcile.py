"""未約定注文の照合処理 (寄成注文の約定単価を翌サイクルで実績に補正する)"""

import numpy as np
import pytest

from autotrader.config import Config
from autotrader.manager import TradingManager
from autotrader.portfolio.portfolio import Portfolio
from tests.conftest import make_ohlcv


def pending_buy(cash=1_000_000, price=2000.0, qty=100):
    p = Portfolio(cash=cash)
    p.apply_buy("2026-08-31", "X", qty, price, 0.0, "寄成", order_id="ORD1", settled=False)
    return p


# ---- 約定確定 (settle_trade) -------------------------------------------
def test_settle_buy_higher_than_estimate():
    """暫定2000円で記録 → 実際は2010円で約定。現金と平均取得単価が補正される"""
    p = pending_buy()
    impact = p.settle_trade(0, 2010.0, 0.0)
    assert p.cash == 1_000_000 - 100 * 2010          # 差額1000円を追加で支払う
    assert p.positions["X"].avg_cost == 2010.0
    assert impact == -1000.0
    assert p.trades[0].settled is True
    assert p.trades[0].price == 2010.0


def test_settle_buy_lower_than_estimate():
    p = pending_buy()
    impact = p.settle_trade(0, 1990.0, 0.0)
    assert p.cash == 1_000_000 - 100 * 1990
    assert p.positions["X"].avg_cost == 1990.0
    assert impact == 1000.0


def test_settle_buy_adjusts_average_of_existing_position():
    """既存建玉がある場合、平均取得単価は建玉全体で按分して補正される"""
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2026-08-28", "X", 100, 1000.0, 0.0, "既存")   # 確定済み
    p.apply_buy("2026-08-31", "X", 100, 2000.0, 0.0, "寄成",
                order_id="ORD1", settled=False)
    assert p.positions["X"].avg_cost == 1500.0
    p.settle_trade(1, 2100.0, 0.0)                              # 実際は2100円
    assert p.positions["X"].avg_cost == pytest.approx(1550.0)   # (1000+2100)/2
    assert p.positions["X"].quantity == 200


def test_settle_sell():
    p = Portfolio(cash=100_000)
    p.apply_buy("2026-08-28", "X", 100, 1000.0, 0.0, "既存")
    assert p.cash == 0
    p.apply_sell("2026-08-31", "X", 100, 2000.0, 0.0, "寄成",
                 order_id="ORD1", settled=False)
    assert p.cash == 200_000
    p.settle_trade(1, 2050.0, 0.0)
    assert p.cash == 205_000     # 想定より50円高く売れた


# ---- 不成立の巻き戻し (cancel_trade) -----------------------------------
def test_cancel_buy_restores_cash_and_removes_position():
    p = pending_buy()
    p.cancel_trade(0, "未約定のため取消")
    assert p.cash == 1_000_000
    assert "X" not in p.positions
    assert p.trades[0].quantity == 0        # 集計対象から外れる
    assert "不成立: 100株" in p.trades[0].reason


def test_cancel_buy_keeps_prior_position_intact():
    """既存建玉がある銘柄の買い増しが不成立でも、元の建玉は保たれる"""
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2026-08-28", "X", 100, 1000.0, 0.0, "既存")
    cash_after_first = p.cash
    p.apply_buy("2026-08-31", "X", 100, 2000.0, 0.0, "寄成",
                order_id="ORD1", settled=False)
    p.cancel_trade(1, "未約定のため取消")
    assert p.cash == cash_after_first
    assert p.positions["X"].quantity == 100
    assert p.positions["X"].avg_cost == 1000.0   # 元の取得単価に戻る


def test_cancel_sell_restores_position():
    p = Portfolio(cash=123_400)
    p.apply_buy("2026-08-28", "X", 100, 1234.0, 0.0, "既存")
    assert p.cash == 0
    p.apply_sell("2026-08-31", "X", 100, 2000.0, 0.0, "寄成",
                 order_id="ORD1", settled=False)
    assert "X" not in p.positions
    p.cancel_trade(1, "未約定のため取消")
    assert p.cash == 0
    assert p.positions["X"].quantity == 100
    assert p.positions["X"].avg_cost == 1234.0   # 売却前の取得単価が復元される


def test_settle_is_idempotent():
    p = pending_buy()
    p.settle_trade(0, 2010.0, 0.0)
    cash = p.cash
    p.settle_trade(0, 2500.0, 0.0)   # 2回目は無視される
    assert p.cash == cash


# ---- マネージャ統合 ----------------------------------------------------
class FakeBroker:
    """照合APIを持つブローカーの代役。新規発注は即時約定として扱う"""

    def __init__(self, results):
        self.results = results

    def fetch_fill(self, order_id):
        return self.results[order_id]

    def execute(self, ticker, side, quantity, ref_price):
        from autotrader.execution.broker import Fill

        return Fill(ticker, side, quantity, round(ref_price, 2), 0.0, "NEW", False)


def make_manager(portfolio, broker=None):
    cfg = Config(universe=["X"], initial_capital=1_000_000, state_file="/tmp/none.json")
    m = TradingManager(cfg, portfolio, persist_state=False)
    if broker is not None:
        m.broker = broker
    return m


def test_reconcile_reports_filled_and_dead():
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2026-08-31", "A", 100, 2000.0, 0.0, "寄成", order_id="O1", settled=False)
    p.apply_buy("2026-08-31", "B", 100, 3000.0, 0.0, "寄成", order_id="O2", settled=False)
    p.apply_buy("2026-08-31", "C", 100, 1000.0, 0.0, "寄成", order_id="O3", settled=False)
    m = make_manager(p, FakeBroker({
        "O1": ("filled", 2010.0, 0.0),
        "O2": ("dead", 0.0, 0.0),
        "O3": ("working", 0.0, 0.0),
    }))
    notes = m.reconcile_pending()

    assert any("A" in n and "約定確定" in n for n in notes)
    assert any("B" in n and "取消" in n for n in notes)
    assert any("C" in n and "未約定" in n for n in notes)
    assert p.positions["A"].avg_cost == 2010.0
    assert "B" not in p.positions                 # 不成立で巻き戻し
    assert p.trades[2].settled is False           # 継続中はそのまま持ち越し


def test_paper_broker_has_no_reconciliation():
    """ペーパートレードは照合APIを持たないため何もしない"""
    p = pending_buy()
    m = make_manager(p)              # PaperBroker
    assert m.reconcile_pending() == []
    assert p.trades[0].settled is False


def test_reconcile_survives_api_error():
    p = pending_buy()

    class Broken:
        def fetch_fill(self, order_id):
            raise RuntimeError("接続エラー")

    m = make_manager(p, Broken())
    notes = m.reconcile_pending()
    assert any("再試行" in n for n in notes)
    assert p.trades[0].settled is False   # 失敗時は状態を変えない


def test_reconcile_runs_before_new_trades(uptrend_df):
    """照合はサイクル冒頭で走り、同一銘柄の新規売買より前に完了する"""
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2026-08-31", "UP", 100, 1000.0, 0.0, "寄成",
                order_id="O1", settled=False)
    m = make_manager(p, FakeBroker({"O1": ("filled", 1100.0, 0.0)}))
    result = m.run_cycle({"UP": uptrend_df}, execute=True)
    assert any("約定確定" in n for n in result.reconciled)
    assert p.trades[0].settled is True
