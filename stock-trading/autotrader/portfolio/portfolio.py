"""ポートフォリオ状態の管理と永続化"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field


@dataclass
class Position:
    ticker: str
    quantity: int
    avg_cost: float


@dataclass
class Trade:
    date: str
    ticker: str
    side: str  # BUY / SELL
    quantity: int
    price: float
    commission: float
    reason: str


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    # ---- 評価 -------------------------------------------------------------
    def position_value(self, ticker: str, price: float) -> float:
        pos = self.positions.get(ticker)
        return pos.quantity * price if pos else 0.0

    def equity(self, prices: dict[str, float]) -> float:
        """現金 + 保有株の評価額。prices に無い保有銘柄は取得価格で評価"""
        total = self.cash
        for t, pos in self.positions.items():
            total += pos.quantity * prices.get(t, pos.avg_cost)
        return total

    def gross_exposure(self, prices: dict[str, float]) -> float:
        eq = self.equity(prices)
        if eq <= 0:
            return 0.0
        invested = sum(
            pos.quantity * prices.get(t, pos.avg_cost) for t, pos in self.positions.items()
        )
        return invested / eq

    # ---- 約定の反映 -------------------------------------------------------
    def apply_buy(self, date: str, ticker: str, qty: int, price: float,
                  commission: float, reason: str) -> None:
        cost = qty * price + commission
        if cost > self.cash + 1e-6:
            raise ValueError(f"{ticker}: 現金不足 (必要 {cost:,.0f} / 保有 {self.cash:,.0f})")
        self.cash -= cost
        pos = self.positions.get(ticker)
        if pos:
            total_qty = pos.quantity + qty
            pos.avg_cost = (pos.avg_cost * pos.quantity + price * qty) / total_qty
            pos.quantity = total_qty
        else:
            self.positions[ticker] = Position(ticker, qty, price)
        self.trades.append(Trade(date, ticker, "BUY", qty, price, commission, reason))

    def apply_sell(self, date: str, ticker: str, qty: int, price: float,
                   commission: float, reason: str) -> None:
        pos = self.positions.get(ticker)
        if not pos or pos.quantity < qty:
            raise ValueError(f"{ticker}: 保有数量不足")
        self.cash += qty * price - commission
        pos.quantity -= qty
        if pos.quantity == 0:
            del self.positions[ticker]
        self.trades.append(Trade(date, ticker, "SELL", qty, price, commission, reason))

    # ---- 永続化 -----------------------------------------------------------
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            "cash": self.cash,
            "positions": {t: asdict(p) for t, p in self.positions.items()},
            "trades": [asdict(tr) for tr in self.trades],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str, initial_capital: float) -> "Portfolio":
        """状態ファイルがあれば復元、なければ初期資金で新規作成"""
        if not os.path.exists(path):
            return cls(cash=initial_capital)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            cash=data["cash"],
            positions={t: Position(**p) for t, p in data.get("positions", {}).items()},
            trades=[Trade(**tr) for tr in data.get("trades", [])],
        )
