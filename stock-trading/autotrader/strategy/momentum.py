"""モメンタム戦略: SMAクロスと20日リターンでトレンド追随"""

from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


class MomentumStrategy(Strategy):
    name = "momentum"

    def evaluate(self, ticker: str, df: pd.DataFrame) -> Signal:
        row = df.iloc[-1]
        if pd.isna(row["sma_long"]) or pd.isna(row["ret_20d"]):
            return Signal(ticker, 0.0, "データ不足")

        # SMAクロス: 乖離±2%で満点になる段階スコア
        gap = (row["sma_short"] - row["sma_long"]) / row["sma_long"]
        gap_score = max(-1.0, min(1.0, gap / 0.02)) * 0.5

        # 20日モメンタム: ±8%で満点になる段階スコア
        mom = row["ret_20d"]
        mom_score = max(-1.0, min(1.0, mom / 0.08)) * 0.5

        score = gap_score + mom_score
        reasons = []
        if abs(gap) > 0.005:
            reasons.append(f"SMA20/60乖離 {gap:+.1%}")
        if abs(mom) > 0.02:
            reasons.append(f"20日リターン {mom:+.1%}")
        return Signal(ticker, max(-1.0, min(1.0, score)), "; ".join(reasons) or "中立")
