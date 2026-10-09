"""資金150万円での目標再設定シミュレーション

実データバックテスト (2023-09〜2026-08: 年率+11.8% / ボラ15.4% / Sharpe 0.76)
を基準に、戦略・リスク設定のシナリオ別で将来の資産分布と目標到達確率を推定する。

  python analysis/target_plan.py
"""

from __future__ import annotations

import numpy as np

N_PATHS = 100_000
START = 1_500_000
# 2026-08-26 時点の残り営業日 / 2027年 / 2028年
SEGMENTS = [("2026年末", 87), ("2027年末", 245), ("2028年末", 245)]

# シナリオ: (名前, 年率リターンμ, 年率ボラσ)
SCENARIOS = [
    ("実測ベース (プランA現物・実績Sharpe0.76)", 0.12, 0.16),
    ("改善ケース (スクリーニング寄与を想定)   ", 0.18, 0.19),
    ("プランB (フル投資・集中)                ", 0.16, 0.26),
    ("信用2倍 (エッジ実証後の将来オプション)  ", 0.21, 0.33),
]

# 到達確率を出す目標候補 (時点ごと)
TARGETS = {
    "2026年末": [1_600_000, 1_700_000, 1_800_000],
    "2027年末": [1_800_000, 2_000_000, 2_500_000],
    "2028年末": [2_000_000, 2_500_000, 3_000_000],
}


def main() -> None:
    rng = np.random.default_rng(20260826)
    print("=" * 100)
    print(f" 前提: 資金 {START:,.0f} 円 / 2026-08-26 開始 / 現物 (レバレッジなし、信用2倍シナリオのみ例外)")
    print("=" * 100)

    for name, mu, sigma in SCENARIOS:
        mu_d, s_d = mu / 252, sigma / np.sqrt(252)
        equity = np.full(N_PATHS, START, dtype=float)
        print(f"\n--- {name} (年率 {mu:+.0%} / ボラ {sigma:.0%}) ---")
        for label, days in SEGMENTS:
            r = rng.normal(mu_d, s_d, (days, N_PATHS))
            equity *= np.prod(1 + np.maximum(r, -0.5), axis=0)
            q25, q50, q75 = np.percentile(equity, [25, 50, 75])
            probs = "  ".join(
                f"P(≥{t/1e4:,.0f}万)={np.mean(equity >= t)*100:4.0f}%" for t in TARGETS[label]
            )
            print(f"  {label}: 中央値 {q50/1e4:,.0f}万 (25-75%: {q25/1e4:,.0f}〜{q75/1e4:,.0f}万)  {probs}")
        print(f"  下振れ: P(2028年末に元本割れ) = {np.mean(equity < START)*100:.0f}%"
              f" / P(120万未満) = {np.mean(equity < 1_200_000)*100:.0f}%")


if __name__ == "__main__":
    main()
