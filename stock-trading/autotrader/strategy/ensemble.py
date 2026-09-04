"""複数戦略のシグナルを重み付きで統合する"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import StrategyConfig
from .base import Signal
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy


@dataclass
class CombinedSignal:
    ticker: str
    score: float
    action: str  # BUY / SELL / HOLD
    details: list[Signal]

    @property
    def reason(self) -> str:
        return " | ".join(f"[{d.reason}]" for d in self.details)


class EnsembleStrategy:
    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.momentum = MomentumStrategy()
        self.mean_reversion = MeanReversionStrategy()

    def evaluate(self, ticker: str, df: pd.DataFrame) -> CombinedSignal:
        mom = self.momentum.evaluate(ticker, df)
        rev = self.mean_reversion.evaluate(ticker, df)
        total_w = self.cfg.momentum_weight + self.cfg.mean_reversion_weight
        score = (
            mom.score * self.cfg.momentum_weight + rev.score * self.cfg.mean_reversion_weight
        ) / total_w

        if score >= self.cfg.buy_threshold:
            action = "BUY"
        elif score <= self.cfg.sell_threshold:
            action = "SELL"
        else:
            action = "HOLD"
        return CombinedSignal(ticker, score, action, [mom, rev])
