"""リスク管理: ポジションサイズ決定と注文の事前チェック

全体管理者(TradingManager)が生成した売買候補は、必ずここを通過してから
執行される。ルールに反する注文は拒否または縮小される。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import RiskConfig
from ..portfolio.portfolio import Portfolio
from .metrics import historical_var


@dataclass
class RiskDecision:
    approved: bool
    quantity: int
    reason: str


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    # ---- 保有ポジションの強制決済判定 -------------------------------------
    def check_exit(self, ticker: str, avg_cost: float, price: float) -> str | None:
        """損切り・利確ラインに達していれば理由文字列を返す"""
        if avg_cost <= 0:
            return None
        change = (price - avg_cost) / avg_cost
        if change <= -self.cfg.stop_loss_pct:
            return f"損切り: 取得比 {change:.1%} <= -{self.cfg.stop_loss_pct:.0%}"
        if change >= self.cfg.take_profit_pct:
            return f"利確: 取得比 +{change:.1%} >= +{self.cfg.take_profit_pct:.0%}"
        return None

    # ---- 新規買い注文のサイズ決定とチェック -------------------------------
    def size_buy(
        self,
        portfolio: Portfolio,
        ticker: str,
        price: float,
        signal_score: float,
        returns: pd.Series | None = None,
        lot_size: int = 100,
    ) -> RiskDecision:
        """買い注文の株数を決定する。

        - シグナル強度に応じて最大配分(max_position_weight)の範囲で配分
        - ボラティリティ(VaR)が高い銘柄は配分を減らす
        - 総エクスポージャーと現金余力の制限を守る
        """
        equity = portfolio.equity({ticker: price})
        if price <= 0 or equity <= 0:
            return RiskDecision(False, 0, "価格または資産が不正")

        # シグナル強度でスケール (score 0.35 -> 約半分, 1.0 -> 満額)
        target_weight = self.cfg.max_position_weight * min(1.0, abs(signal_score) + 0.3)

        # 銘柄VaRが高いほど配分を絞る (日次VaR 2%を基準に逆比例)
        if returns is not None:
            var = historical_var(returns)
            if var > 0.02:
                target_weight *= 0.02 / var

        current_value = portfolio.position_value(ticker, price)
        current_weight = current_value / equity
        add_weight = max(0.0, target_weight - current_weight)
        if add_weight <= 0.01:
            return RiskDecision(False, 0, f"既に配分上限付近 ({current_weight:.0%})")

        # 総エクスポージャー制限
        gross = portfolio.gross_exposure({ticker: price})
        room = self.cfg.max_gross_exposure - gross
        if room <= 0.01:
            return RiskDecision(False, 0, f"総エクスポージャー上限 ({gross:.0%})")
        add_weight = min(add_weight, room)

        budget = min(equity * add_weight, portfolio.cash * 0.98)
        qty = int(budget / price / lot_size) * lot_size
        if qty <= 0:
            return RiskDecision(False, 0, "予算内で最低単元に届かず")
        return RiskDecision(True, qty, f"目標配分 {target_weight:.0%} に対し {qty} 株")

    # ---- ポートフォリオ全体のVaRチェック ----------------------------------
    def portfolio_var_ok(self, portfolio_returns: pd.Series) -> tuple[bool, float]:
        var = historical_var(portfolio_returns)
        return var <= self.cfg.max_daily_var_pct, var
