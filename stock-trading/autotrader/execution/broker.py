"""ブローカー抽象インターフェース

実際の証券会社API(例: 立花証券, kabuステーション, IB等)に接続する場合は
このインターフェースを実装したアダプタを追加し、設定で明示的に切り替える。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Fill:
    """約定結果"""

    ticker: str
    side: str  # BUY / SELL
    quantity: int
    price: float       # 約定単価 (スリッページ込み)
    commission: float
    order_id: str = ""   # 実弾モードの注文番号 (照合に使う)
    pending: bool = False  # True=まだ約定しておらず price は参照価格の暫定値


class Broker(ABC):
    @abstractmethod
    def execute(self, ticker: str, side: str, quantity: int, ref_price: float) -> Fill:
        """注文を執行し約定結果を返す。ref_price は直近の市場価格"""
