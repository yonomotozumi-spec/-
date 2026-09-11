import numpy as np

from autotrader.backtest.engine import BacktestEngine
from autotrader.config import Config
from autotrader.manager import TradingManager
from autotrader.portfolio.portfolio import Portfolio
from tests.conftest import make_ohlcv


def make_cfg(tmp_path=None):
    cfg = Config(universe=["UP", "DOWN"], initial_capital=3_000_000)
    if tmp_path is not None:
        cfg.state_file = str(tmp_path / "portfolio.json")
    return cfg


def test_cycle_buys_uptrend_and_ignores_downtrend(uptrend_df, downtrend_df, tmp_path):
    cfg = make_cfg(tmp_path)
    manager = TradingManager(cfg, Portfolio(cash=cfg.initial_capital))
    result = manager.run_cycle({"UP": uptrend_df, "DOWN": downtrend_df}, execute=True)

    buys = [i for i in result.instructions if i.action == "BUY" and i.executed]
    assert any(i.ticker == "UP" for i in buys)
    assert "UP" in manager.portfolio.positions
    assert "DOWN" not in manager.portfolio.positions  # 保有していない銘柄の売りシグナルは無視


def test_advise_mode_does_not_execute(uptrend_df, tmp_path):
    cfg = make_cfg(tmp_path)
    manager = TradingManager(cfg, Portfolio(cash=cfg.initial_capital))
    result = manager.run_cycle({"UP": uptrend_df}, execute=False)
    assert manager.portfolio.cash == cfg.initial_capital
    assert not manager.portfolio.positions
    assert all(not i.executed for i in result.instructions)


def test_stop_loss_exit_executes(uptrend_df, tmp_path):
    cfg = make_cfg(tmp_path)
    p = Portfolio(cash=1_000_000)
    last_price = float(uptrend_df["close"].iloc[-1])
    # 現値より大幅に高い取得価格 → 損切り対象
    p.apply_buy("2024-01-05", "UP", 100, last_price * 1.5, 0, "")
    manager = TradingManager(cfg, p)
    result = manager.run_cycle({"UP": uptrend_df}, execute=True)

    sells = [i for i in result.instructions if i.action == "SELL" and i.executed]
    assert sells and "損切り" in sells[0].reason


def test_report_structure(uptrend_df, tmp_path):
    cfg = make_cfg(tmp_path)
    manager = TradingManager(cfg, Portfolio(cash=cfg.initial_capital))
    manager.run_cycle({"UP": uptrend_df}, execute=True)
    report = manager.report({"UP": uptrend_df})
    assert report["equity"] > 0
    assert isinstance(report["holdings"], list)
    if report["holdings"]:
        assert "risk" in report and "var_95" in report["risk"]


def test_backtest_runs_and_reports(tmp_path):
    rng = np.random.default_rng(3)
    up = make_ohlcv(1000 * np.cumprod(1 + 0.003 + rng.normal(0, 0.01, 250)))
    noise = make_ohlcv(2000 * np.cumprod(1 + rng.normal(0, 0.01, 250)))

    cfg = make_cfg(tmp_path)
    result = BacktestEngine(cfg).run({"UP": up, "NOISE": noise})

    assert result.final_equity > 0
    assert len(result.equity_curve) > 100
    assert "sharpe" in result.metrics
    # バックテストは本番の状態ファイルを書き換えない
    assert not (tmp_path / "portfolio.json").exists()
