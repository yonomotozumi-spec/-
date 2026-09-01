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
    peak_price: float = 0.0  # 保有開始後の最高値 (トレーリングストップの基準)


@dataclass
class Trade:
    date: str
    ticker: str
    side: str  # BUY / SELL
    quantity: int
    price: float
    commission: float
    reason: str
    # 実弾モードで寄成注文を出した直後は約定価格が未確定になる。
    # 翌サイクル冒頭の照合処理で実績に補正するまで settled=False のまま。
    order_id: str = ""
    settled: bool = True
    prev_avg_cost: float = 0.0  # 取消時に建玉を復元するための約定前の平均取得単価


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
                  commission: float, reason: str,
                  order_id: str = "", settled: bool = True) -> None:
        cost = qty * price + commission
        if cost > self.cash + 1e-6:
            raise ValueError(f"{ticker}: 現金不足 (必要 {cost:,.0f} / 保有 {self.cash:,.0f})")
        prev_avg = self.positions[ticker].avg_cost if ticker in self.positions else 0.0
        self.cash -= cost
        pos = self.positions.get(ticker)
        if pos:
            total_qty = pos.quantity + qty
            pos.avg_cost = (pos.avg_cost * pos.quantity + price * qty) / total_qty
            pos.quantity = total_qty
        else:
            self.positions[ticker] = Position(ticker, qty, price, price)
        self.trades.append(Trade(date, ticker, "BUY", qty, price, commission, reason,
                                 order_id, settled, prev_avg))

    def apply_sell(self, date: str, ticker: str, qty: int, price: float,
                   commission: float, reason: str,
                   order_id: str = "", settled: bool = True) -> None:
        pos = self.positions.get(ticker)
        if not pos or pos.quantity < qty:
            raise ValueError(f"{ticker}: 保有数量不足")
        prev_avg = pos.avg_cost
        self.cash += qty * price - commission
        pos.quantity -= qty
        if pos.quantity == 0:
            del self.positions[ticker]
        self.trades.append(Trade(date, ticker, "SELL", qty, price, commission, reason,
                                 order_id, settled, prev_avg))

    # ---- 未確定注文の照合 ---------------------------------------------------
    def pending_trades(self) -> list[tuple[int, "Trade"]]:
        """約定価格が未確定の取引を (インデックス, Trade) で返す"""
        return [(i, t) for i, t in enumerate(self.trades)
                if not t.settled and t.order_id]

    def settle_trade(self, index: int, actual_price: float,
                     actual_commission: float) -> float:
        """未確定取引を実際の約定単価で補正し、資産への影響額を返す。

        照合はサイクル冒頭 (新規売買の前) に行うため、対象銘柄に対して
        この取引以降の売買は無いことが保証される。
        """
        t = self.trades[index]
        if t.settled:
            return 0.0
        dp = actual_price - t.price
        dc = actual_commission - t.commission
        if t.side == "BUY":
            self.cash -= dp * t.quantity + dc
            pos = self.positions.get(t.ticker)
            if pos and pos.quantity > 0:
                pos.avg_cost = (pos.avg_cost * pos.quantity + dp * t.quantity) / pos.quantity
            impact = -(dp * t.quantity + dc)
        else:
            self.cash += dp * t.quantity - dc
            impact = dp * t.quantity - dc
        t.price, t.commission, t.settled = actual_price, actual_commission, True
        return impact

    def cancel_trade(self, index: int, note: str) -> None:
        """約定しなかった取引を取り消し、現金と建玉を元に戻す"""
        t = self.trades[index]
        if t.settled:
            return
        if t.side == "BUY":
            self.cash += t.quantity * t.price + t.commission
            pos = self.positions.get(t.ticker)
            if pos:
                remain = pos.quantity - t.quantity
                if remain <= 0:
                    del self.positions[t.ticker]
                else:
                    pos.quantity = remain
                    pos.avg_cost = t.prev_avg_cost or pos.avg_cost
        else:
            self.cash -= t.quantity * t.price - t.commission
            pos = self.positions.get(t.ticker)
            if pos:
                pos.quantity += t.quantity
            else:
                self.positions[t.ticker] = Position(
                    t.ticker, t.quantity, t.prev_avg_cost or t.price)
            self.positions[t.ticker].avg_cost = t.prev_avg_cost or t.price
        t.settled = True
        # 数量を0にして損益・勝敗の集計対象から外す。何株の注文だったかは
        # 監査のため理由欄に残す。
        t.reason += f" / {note} (不成立: {t.quantity}株)"
        t.quantity = 0

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
