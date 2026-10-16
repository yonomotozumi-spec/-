"""戦略の基底クラスとシグナル定義"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class Signal:
    """1銘柄に対する戦略シグナル。score は -1.0(強い売り) 〜 +1.0(強い買い)"""

    ticker: str
    score: float
    reason: str


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def evaluate(self, ticker: str, df: pd.DataFrame) -> Signal:
        """指標付き日足データからシグナルを算出する"""
