"""平均回帰戦略: RSI とボリンジャーバンドで行き過ぎを検出"""

from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def evaluate(self, ticker: str, df: pd.DataFrame) -> Signal:
        row = df.iloc[-1]
        if pd.isna(row["rsi"]) or pd.isna(row["bb_z"]) or pd.isna(row["sma_long"]):
            return Signal(ticker, 0.0, "データ不足")

        # トレンドフィルタ: 強いトレンド(SMA乖離±3%超)には逆張りしない
        trend = (row["sma_short"] - row["sma_long"]) / row["sma_long"]

        score = 0.0
        reasons = []

        # RSI: 30以下は売られすぎ(買い)、70以上は買われすぎ(売り)
        if row["rsi"] <= 30:
            if trend < -0.03:
                reasons.append(f"RSI {row['rsi']:.0f} だが強い下降トレンドのため逆張り抑制")
            else:
                score += 0.5
                reasons.append(f"RSI {row['rsi']:.0f} 売られすぎ")
        elif row["rsi"] >= 70:
            if trend > 0.03:
                reasons.append(f"RSI {row['rsi']:.0f} だが強い上昇トレンドのため逆張り抑制")
            else:
                score -= 0.5
                reasons.append(f"RSI {row['rsi']:.0f} 買われすぎ")

        # ボリンジャーバンド: -2σ以下で買い、+2σ以上で売り (同じくトレンドフィルタ適用)
        if row["bb_z"] <= -2 and trend >= -0.03:
            score += 0.5
            reasons.append(f"BB {row['bb_z']:.1f}σ 下限割れ")
        elif row["bb_z"] >= 2 and trend <= 0.03:
            score -= 0.5
            reasons.append(f"BB +{row['bb_z']:.1f}σ 上限超え")

        return Signal(ticker, max(-1.0, min(1.0, score)), "; ".join(reasons) or "中立")
