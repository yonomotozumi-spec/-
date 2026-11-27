"""ペーパートレード執行: 市場価格にスリッページと手数料を加味した仮想約定"""

from __future__ import annotations

from ..config import ExecutionConfig
from .broker import Broker, Fill


class PaperBroker(Broker):
    def __init__(self, cfg: ExecutionConfig):
        self.cfg = cfg

    def execute(self, ticker: str, side: str, quantity: int, ref_price: float) -> Fill:
        if quantity <= 0 or ref_price <= 0:
            raise ValueError("数量・価格が不正です")
        slip = ref_price * self.cfg.slippage_pct
        price = ref_price + slip if side == "BUY" else ref_price - slip
        commission = quantity * price * self.cfg.commission_pct
        return Fill(ticker, side, quantity, round(price, 2), round(commission, 2))
