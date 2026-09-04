"""バックテストエンジン

TradingManager と同じ判断ロジック(戦略 + リスク管理)を過去データ上で
日次に繰り返し、資産曲線とリスク・リターン指標を算出する。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..config import Config
from ..manager import TradingManager
from ..portfolio.portfolio import Portfolio
from ..risk.metrics import summarize


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    metrics: dict[str, float]
    trades: list = field(default_factory=list)
    final_equity: float = 0.0


class BacktestEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def run(
        self,
        market_data: dict[str, pd.DataFrame],
        start: str | None = None,
        warmup: int = 70,
    ) -> BacktestResult:
        """market_data は指標計算済みの全期間データ。

        warmup 日分は指標の計算のために確保し、それ以降を検証期間とする。
        各営業日について「その日までのデータ」だけで判断する (先読みなし)。
        """
        # 共通の営業日インデックスを作る
        all_dates = sorted(set().union(*[set(df.index) for df in market_data.values()]))
        if start:
            trade_dates = [d for d in all_dates[warmup:] if d >= pd.Timestamp(start)]
        else:
            trade_dates = all_dates[warmup:]
        if not trade_dates:
            raise ValueError("検証期間が空です。データ期間と start を確認してください")

        portfolio = Portfolio(cash=self.cfg.initial_capital)
        manager = TradingManager(self.cfg, portfolio, persist_state=False)

        equity_hist: dict[pd.Timestamp, float] = {}
        for date in trade_dates:
            # その日までのデータに切り詰める (指標は事前計算済みなのでスライスのみ)
            snapshot = {
                t: df.loc[:date]
                for t, df in market_data.items()
                if len(df.loc[:date]) > warmup and df.index[-1] >= date
            }
            snapshot = {t: df for t, df in snapshot.items() if df.index[-1] == date}
            if not snapshot:
                continue
            manager.run_cycle(snapshot, execute=True, as_of=str(date.date()))
            prices = {t: float(df["close"].iloc[-1]) for t, df in snapshot.items()}
            equity_hist[date] = portfolio.equity(prices)

        equity_curve = pd.Series(equity_hist).sort_index()
        returns = equity_curve.pct_change()
        return BacktestResult(
            equity_curve=equity_curve,
            metrics=summarize(returns, self.cfg.risk.risk_free_rate),
            trades=portfolio.trades,
            final_equity=float(equity_curve.iloc[-1]),
        )
