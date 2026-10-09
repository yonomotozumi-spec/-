"""損切り直後の買い戻し禁止 (クールダウン)"""

import numpy as np
import pandas as pd

from autotrader.data.market_data import add_indicators
from autotrader.config import Config, ExecutionConfig, RiskConfig, StrategyConfig
from autotrader.manager import TradingManager
from autotrader.strategy.ensemble import CombinedSignal
from autotrader.portfolio.portfolio import Portfolio


def falling_market(n: int = 200, start: float = 1000.0, drop: float = 0.004):
    """じわじわ下げる日足 (逆張りシグナルが出る形)"""
    idx = pd.bdate_range("2026-01-01", periods=n)
    close = pd.Series(start * np.exp(-drop * np.arange(n)), index=idx)
    return add_indicators(pd.DataFrame({
        "open": close, "high": close, "low": close,
        "close": close, "volume": 1_000_000.0,
    }))


def make_cfg(cooldown: int) -> Config:
    return Config(
        universe=["X"],
        initial_capital=1_000_000,
        risk=RiskConfig(stop_loss_pct=0.08, take_profit_pct=0.0,
                        trailing_stop_pct=0.0, stop_cooldown_days=cooldown),
        strategy=StrategyConfig(),
        execution=ExecutionConfig(mode="paper", commission_pct=0.0,
                                  slippage_pct=0.0, lot_size=100),
        state_file="/tmp/does-not-matter.json",
    )


def run_stop_out(cooldown: int):
    """含み損8%超のポジションを持たせて1サイクル回す"""
    df = falling_market()
    price = float(df["close"].iloc[-1])
    pf = Portfolio(cash=1_000_000)
    pf.apply_buy("2026-09-10", "X", 100, price / 0.90, 0, "")  # -10%の含み損
    mgr = TradingManager(make_cfg(cooldown), portfolio=pf, persist_state=False)
    result = mgr.run_cycle({"X": df}, as_of="2026-09-11")
    return mgr, result


def test_stop_loss_records_cooldown():
    mgr, result = run_stop_out(5)
    sells = [i for i in result.instructions if i.action == "SELL"]
    assert sells and sells[0].reason.startswith("損切り")
    assert mgr.portfolio.stop_cooldown.get("X") == "2026-09-11"
    # 同一サイクルで買い戻していない
    assert not [i for i in result.instructions if i.action == "BUY"]


class AlwaysBuy:
    """常に買いシグナルを返すスタブ (合成データの形に依存させないため)"""

    def evaluate(self, ticker, df):
        return CombinedSignal(ticker, 0.8, "BUY", [])


def test_cooldown_blocks_buy_next_day():
    mgr, _ = run_stop_out(5)
    mgr.strategy = AlwaysBuy()
    result = mgr.run_cycle({"X": falling_market()}, as_of="2026-09-14")
    assert not [i for i in result.instructions if i.action == "BUY"]
    assert any("クールダウン 残り4営業日" in w for w in result.warnings)


def test_cooldown_expires_and_allows_buy():
    mgr, _ = run_stop_out(5)
    mgr.strategy = AlwaysBuy()
    # 5営業日後は解除され、買いが通り、記録も消える
    result = mgr.run_cycle({"X": falling_market()}, as_of="2026-09-18")
    assert [i for i in result.instructions if i.action == "BUY"]
    assert "X" not in mgr.portfolio.stop_cooldown


def test_cooldown_disabled_allows_immediate_rebuy():
    """クールダウン0なら記録もせず従来どおり (回帰の検出用)"""
    mgr, _ = run_stop_out(0)
    assert mgr.portfolio.stop_cooldown == {}
    mgr.strategy = AlwaysBuy()
    result = mgr.run_cycle({"X": falling_market()}, as_of="2026-09-14")
    assert [i for i in result.instructions if i.action == "BUY"]


def test_cooldown_survives_save_load(tmp_path):
    mgr, _ = run_stop_out(5)
    path = tmp_path / "portfolio.json"
    mgr.portfolio.save(str(path))
    reloaded = Portfolio.load(str(path), 1_000_000)
    assert reloaded.stop_cooldown == {"X": "2026-09-11"}
