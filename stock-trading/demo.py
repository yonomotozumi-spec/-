"""合成データによるデモ (ネットワーク不要)

実データが取得できない環境でも、システム全体の動作
(シグナル → リスク判定 → 執行 → レポート → バックテスト) を確認できる。

  python demo.py
"""

from __future__ import annotations

import numpy as np

from autotrader.backtest.engine import BacktestEngine
from autotrader.config import Config
from autotrader.manager import TradingManager
from autotrader.portfolio.portfolio import Portfolio
from tests.conftest import make_ohlcv
from main import print_cycle


def make_universe() -> dict:
    rng = np.random.default_rng(2024)
    return {
        "DEMO-UP.T": make_ohlcv(2500 * np.cumprod(1 + 0.003 + rng.normal(0, 0.010, 300))),
        "DEMO-DOWN.T": make_ohlcv(1800 * np.cumprod(1 - 0.002 + rng.normal(0, 0.012, 300))),
        "DEMO-FLAT.T": make_ohlcv(3200 * np.cumprod(1 + rng.normal(0, 0.008, 300))),
    }


def main() -> None:
    data = make_universe()
    cfg = Config(
        universe=list(data),
        initial_capital=3_000_000,
        state_file="state/demo_portfolio.json",
    )

    print("=" * 60)
    print(" デモ1: 売買指示サイクル (ペーパートレード執行)")
    print("=" * 60)
    manager = TradingManager(cfg, Portfolio(cash=cfg.initial_capital), persist_state=False)
    result = manager.run_cycle(data, execute=True)
    print_cycle(result, executed=True)

    print()
    print("=" * 60)
    print(" デモ2: バックテスト (約230営業日)")
    print("=" * 60)
    bt = BacktestEngine(cfg).run(data)
    m = bt.metrics
    print(f"  初期資金:   {cfg.initial_capital:>12,.0f} 円")
    print(f"  最終資産:   {bt.final_equity:>12,.0f} 円 "
          f"({(bt.final_equity / cfg.initial_capital - 1) * 100:+.2f}%)")
    print(f"  年率リターン {m['annual_return']:+.1%} / ボラ {m['annual_volatility']:.1%} / "
          f"シャープ {m['sharpe']:.2f}")
    print(f"  最大DD {m['max_drawdown']:.1%} / 日次VaR95 {m['var_95']:.2%} / "
          f"取引 {len(bt.trades)} 回")


if __name__ == "__main__":
    main()
