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
    def check_exit(self, ticker: str, avg_cost: float, price: float,
                   peak_price: float = 0.0) -> str | None:
        """損切り・利確ラインに達していれば理由文字列を返す。

        判定順は 損切り → 固定利確 → トレーリング利確。
        トレーリングは「高値から一定率下げたら利食う」方式で、上値を
        追い続けられるためトレンドの右裾を切り落とさない。
        """
        if avg_cost <= 0:
            return None
        change = (price - avg_cost) / avg_cost
        if change <= -self.cfg.stop_loss_pct:
            return f"損切り: 取得比 {change:.1%} <= -{self.cfg.stop_loss_pct:.0%}"
        if self.cfg.take_profit_pct > 0 and change >= self.cfg.take_profit_pct:
            return f"利確: 取得比 +{change:.1%} >= +{self.cfg.take_profit_pct:.0%}"
        if self.cfg.trailing_stop_pct > 0 and peak_price > avg_cost:
            trail_line = peak_price * (1 - self.cfg.trailing_stop_pct)
            # 利益を確定できる場合のみ作動 (下回る場合は損切りに委ねる)
            if trail_line > avg_cost and price <= trail_line:
                drop = (price - peak_price) / peak_price
                return (f"トレーリング利確: 高値{peak_price:,.0f}から{drop:.1%} "
                        f"(取得比 +{change:.1%})")
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
        signal_weight = self.cfg.max_position_weight * min(1.0, abs(signal_score) + 0.3)
        target_weight = signal_weight

        # 銘柄VaRが高いほど配分を絞る (日次VaR 2%を基準に逆比例)
        var_scale = 1.0
        if returns is not None:
            var = historical_var(returns)
            if var > 0.02:
                var_scale = 0.02 / var
                target_weight *= var_scale

        current_value = portfolio.position_value(ticker, price)
        current_weight = current_value / equity
        add_weight = max(0.0, target_weight - current_weight)
        if add_weight <= 0.01:
            return RiskDecision(
                False, 0,
                f"既に配分上限付近 (現在 {current_weight:.0%} / 目標 {target_weight:.0%})")

        # 総エクスポージャー制限
        gross = portfolio.gross_exposure({ticker: price})
        room = self.cfg.max_gross_exposure - gross
        if room <= 0.01:
            return RiskDecision(False, 0, f"総エクスポージャー上限 ({gross:.0%})")
        add_weight = min(add_weight, room)

        budget = min(equity * add_weight, portfolio.cash * 0.98)
        qty = int(budget / price / lot_size) * lot_size
        if qty <= 0:
            # 単元株モードでは「目標配分は出たが1単元の値段に届かない」ことで
            # 買いが丸ごと消える。原因の内訳が分かるよう数値を残す。
            detail = (f"目標配分 {target_weight:.0%} = {equity * add_weight:,.0f}円 "
                      f"< 1単元 {price * lot_size:,.0f}円")
            if var_scale < 1.0:
                detail += f" (シグナル {signal_weight:.0%} をVaRで×{var_scale:.2f}に縮小)"
            return RiskDecision(False, 0, f"予算内で最低単元に届かず — {detail}")
        return RiskDecision(True, qty, f"目標配分 {target_weight:.0%} に対し {qty} 株")

    # ---- ポートフォリオ全体のVaRチェック ----------------------------------
    def portfolio_var_ok(self, portfolio_returns: pd.Series) -> tuple[bool, float]:
        var = historical_var(portfolio_returns)
        return var <= self.cfg.max_daily_var_pct, var
