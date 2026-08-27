"""TradingManager — 取引の全体管理者

1サイクルの流れ:
  1. マーケット情報の収集 (価格 + テクニカル指標)
  2. 保有ポジションの損切り・利確判定 (最優先)
  3. 戦略シグナルの統合評価
  4. リスク管理による注文サイズ決定・事前チェック
  5. 執行 (ペーパートレード) と状態保存
  6. リスク・リターンレポートの生成
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from .config import Config
from .execution.paper import PaperBroker
from .portfolio.portfolio import Portfolio
from .risk.manager import RiskManager
from .risk.metrics import summarize
from .strategy.ensemble import EnsembleStrategy


@dataclass
class Instruction:
    """全体管理者が発行する売買指示"""

    ticker: str
    action: str          # BUY / SELL / HOLD
    quantity: int
    price: float
    score: float
    reason: str
    executed: bool = False


@dataclass
class CycleResult:
    date: str
    instructions: list[Instruction] = field(default_factory=list)
    portfolio_summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class TradingManager:
    def __init__(
        self, cfg: Config, portfolio: Portfolio | None = None, persist_state: bool = True
    ):
        self.cfg = cfg
        self.persist_state = persist_state
        self.portfolio = portfolio or Portfolio.load(cfg.state_file, cfg.initial_capital)
        self.strategy = EnsembleStrategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk)
        self.broker = PaperBroker(cfg.execution)

    # ------------------------------------------------------------------
    def run_cycle(
        self,
        market_data: dict[str, pd.DataFrame],
        execute: bool = True,
        as_of: str | None = None,
        buy_allowed: set[str] | None = None,
    ) -> CycleResult:
        """1営業日分の判断サイクルを実行する。

        execute=False の場合は指示の生成のみ行う (advise モード)。
        buy_allowed を指定すると、新規買いはその銘柄に限定する
        (ユニバース外になった保有銘柄は売り判定のみ行われる)。
        """
        date = as_of or dt.date.today().isoformat()
        result = CycleResult(date=date)

        prices = {t: float(df["close"].iloc[-1]) for t, df in market_data.items()}

        # --- 1. 保有ポジションの損切り・利確 (シグナルより優先) ---
        for ticker in list(self.portfolio.positions):
            if ticker not in prices:
                result.warnings.append(f"{ticker}: 価格取得不可のため判定スキップ")
                continue
            pos = self.portfolio.positions[ticker]
            exit_reason = self.risk.check_exit(ticker, pos.avg_cost, prices[ticker])
            if exit_reason:
                inst = Instruction(
                    ticker, "SELL", pos.quantity, prices[ticker], 0.0, exit_reason
                )
                if execute:
                    self._execute(inst, date)
                result.instructions.append(inst)

        # --- 2. 戦略シグナル評価 → 売買指示 ---
        for ticker, df in market_data.items():
            sig = self.strategy.evaluate(ticker, df)
            price = prices[ticker]
            pos = self.portfolio.positions.get(ticker)

            if sig.action == "SELL" and pos and pos.quantity > 0:
                inst = Instruction(
                    ticker, "SELL", pos.quantity, price, sig.score,
                    f"売りシグナル {sig.score:+.2f} {sig.reason}",
                )
            elif sig.action == "BUY":
                if buy_allowed is not None and ticker not in buy_allowed:
                    continue
                decision = self.risk.size_buy(
                    self.portfolio, ticker, price, sig.score, df["ret_1d"],
                    lot_size=self.cfg.execution.lot_size,
                )
                if not decision.approved:
                    result.warnings.append(f"{ticker}: 買い見送り ({decision.reason})")
                    continue
                inst = Instruction(
                    ticker, "BUY", decision.quantity, price, sig.score,
                    f"買いシグナル {sig.score:+.2f} {sig.reason} / {decision.reason}",
                )
            else:
                continue

            if execute:
                self._execute(inst, date)
            result.instructions.append(inst)

        # --- 3. レポート ---
        result.portfolio_summary = self.report(market_data)

        if execute and self.persist_state:
            self.portfolio.save(self.cfg.state_file)
            self._append_equity_log(date, result.portfolio_summary.get("equity", 0))
            self._save_summary(date, result.portfolio_summary)
        return result

    def _save_summary(self, date: str, summary: dict) -> None:
        """最新の評価サマリ (保有の現在値・損益込み) をダッシュボード用に保存"""
        import json
        import os

        path = os.path.join(os.path.dirname(self.cfg.state_file) or ".", "summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": date, **summary}, f, ensure_ascii=False, indent=2)

    def _append_equity_log(self, date: str, equity: float) -> None:
        """日次資産推移を equity_log.csv に追記する (同日分は上書き)"""
        import csv
        import os

        path = os.path.join(os.path.dirname(self.cfg.state_file) or ".", "equity_log.csv")
        rows: list[list[str]] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows = [r for r in csv.reader(f) if r and r[0] not in ("date", date)]
        rows.append([date, f"{equity:.0f}", f"{self.portfolio.cash:.0f}"])
        rows.sort(key=lambda r: r[0])
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "equity", "cash"])
            w.writerows(rows)

    # ------------------------------------------------------------------
    def _execute(self, inst: Instruction, date: str) -> None:
        try:
            fill = self.broker.execute(inst.ticker, inst.action, inst.quantity, inst.price)
            if inst.action == "BUY":
                self.portfolio.apply_buy(
                    date, fill.ticker, fill.quantity, fill.price, fill.commission, inst.reason
                )
            else:
                self.portfolio.apply_sell(
                    date, fill.ticker, fill.quantity, fill.price, fill.commission, inst.reason
                )
            inst.executed = True
        except ValueError as e:
            inst.reason += f" / 執行失敗: {e}"

    # ------------------------------------------------------------------
    def report(self, market_data: dict[str, pd.DataFrame]) -> dict:
        """ポートフォリオの現況とリスク指標をまとめる"""
        prices = {t: float(df["close"].iloc[-1]) for t, df in market_data.items()}
        equity = self.portfolio.equity(prices)

        holdings = []
        for t, pos in self.portfolio.positions.items():
            price = prices.get(t, pos.avg_cost)
            value = pos.quantity * price
            holdings.append(
                {
                    "ticker": t,
                    "quantity": pos.quantity,
                    "avg_cost": round(pos.avg_cost, 2),
                    "price": round(price, 2),
                    "value": round(value, 0),
                    "pnl_pct": round((price - pos.avg_cost) / pos.avg_cost * 100, 2),
                    "weight_pct": round(value / equity * 100, 1) if equity else 0,
                }
            )

        # 現在の保有比率で加重したポートフォリオ日次リターン系列からリスク指標を計算
        port_returns = self._portfolio_returns(market_data, prices, equity)
        risk_metrics = (
            summarize(port_returns, self.cfg.risk.risk_free_rate)
            if port_returns is not None
            else {}
        )
        var_ok = True
        if port_returns is not None:
            var_ok, _ = self.risk.portfolio_var_ok(port_returns)

        return {
            "equity": round(equity, 0),
            "cash": round(self.portfolio.cash, 0),
            "gross_exposure_pct": round(self.portfolio.gross_exposure(prices) * 100, 1),
            "total_return_pct": round(
                (equity - self.cfg.initial_capital) / self.cfg.initial_capital * 100, 2
            ),
            "holdings": holdings,
            "risk": {k: round(v, 4) for k, v in risk_metrics.items()},
            "var_within_limit": var_ok,
        }

    def _portfolio_returns(
        self, market_data: dict[str, pd.DataFrame], prices: dict[str, float], equity: float
    ) -> pd.Series | None:
        if not self.portfolio.positions or equity <= 0:
            return None
        weighted = []
        for t, pos in self.portfolio.positions.items():
            if t not in market_data:
                continue
            w = pos.quantity * prices.get(t, pos.avg_cost) / equity
            weighted.append(market_data[t]["ret_1d"] * w)
        if not weighted:
            return None
        return pd.concat(weighted, axis=1).sum(axis=1, min_count=1).dropna()
