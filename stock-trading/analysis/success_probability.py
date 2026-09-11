"""目標資産到達確率のモンテカルロ試算

計画: 2026-08-24 に 50万円でスタート
  - 2026年末:   200万円 (4.0倍 / 約88営業日)
  - 2027年末:   500万円 (累計10倍)
  - 2028年末: 1,000万円 (累計20倍)

戦略の実力(年率リターンμ・ボラティリティσ)ごとに10万パスを生成し、
各マイルストーンの到達確率と破綻確率を推定する。

  python analysis/success_probability.py
"""

from __future__ import annotations

import numpy as np

N_PATHS = 100_000
START = 500_000
RUIN = 100_000          # これを割ると単元株取引がほぼ不可能 = 実質退場
SEGMENTS = [88, 245, 245]  # 2026残り / 2027 / 2028 の営業日数
MILESTONES = [2_000_000, 5_000_000, 10_000_000]

# シナリオ: (名前, 年率リターン, 年率ボラティリティ)
# Sharpe = μ/σ の目安を併記。個人のシステムトレードで長期Sharpe 1.0超は上位数%。
SCENARIOS = [
    ("堅実運用 (現物・低レバ)          Sharpe≈0.7", 0.10, 0.15),
    ("優秀なシステム (現物集中)        Sharpe≈1.0", 0.25, 0.25),
    ("卓越 (HF上位クラス)              Sharpe≈1.5", 0.45, 0.30),
    ("信用3倍×優秀シグナル             Sharpe≈0.9", 0.80, 0.90),
    ("レバ全開・超集中 (ほぼ賭け)      Sharpe≈0.6", 1.20, 2.00),
]


def simulate(mu: float, sigma: float, rng: np.random.Generator) -> dict:
    mu_d = mu / 252
    sigma_d = sigma / np.sqrt(252)

    equity = np.full(N_PATHS, START, dtype=float)
    alive = np.ones(N_PATHS, dtype=bool)
    hit = np.zeros((len(SEGMENTS), N_PATHS), dtype=bool)

    for seg, days in enumerate(SEGMENTS):
        for _ in range(days):
            r = rng.normal(mu_d, sigma_d, N_PATHS)
            r = np.maximum(r, -0.95)  # 1日の損失は最大95%でクリップ
            equity[alive] *= 1 + r[alive]
            alive &= equity > RUIN
        hit[seg] = alive & (equity >= MILESTONES[seg])

    all_hit = hit[0] & hit[1] & hit[2]
    return {
        "p_m1": hit[0].mean(),
        "p_m2": hit[1].mean(),
        "p_all": all_hit.mean(),
        "p_final_only": (alive & (equity >= MILESTONES[2])).mean(),
        "p_ruin": (~alive).mean(),
        "median_final": float(np.median(equity)),
    }


def main() -> None:
    rng = np.random.default_rng(20260824)
    total_days = sum(SEGMENTS)

    print("=" * 78)
    print(" 目標: 50万 → 200万(2026年末) → 500万(2027年末) → 1,000万(2028年末)")
    print("=" * 78)
    print(f" 必要リターン: 年内 +300% (88営業日で4倍 = 年率換算 約{4**(252/88)*100-100:,.0f}%)")
    print(f"              2027年 +150% / 2028年 +100% / 通算 {total_days}営業日で20倍")
    print()
    print(f"{'シナリオ (戦略の実力)':<44}{'年内200万':>8}{'完全達成':>8}{'28年末1000万':>10}{'破綻':>7}{'中央値':>12}")
    print("-" * 78)
    for name, mu, sigma in SCENARIOS:
        r = simulate(mu, sigma, rng)
        print(
            f"{name:<44}"
            f"{r['p_m1']*100:>7.2f}%"
            f"{r['p_all']*100:>7.2f}%"
            f"{r['p_final_only']*100:>9.2f}%"
            f"{r['p_ruin']*100:>6.1f}%"
            f"{r['median_final']:>11,.0f}円"
        )
    print("-" * 78)
    print(" 完全達成 = 3つのマイルストーンすべて期日内に到達")
    print(" 28年末1000万 = 途中経過を問わず2028年末に1,000万以上 (破綻回避が条件)")
    print(" 破綻 = 資産10万円未満 (単元株取引が実質不可能)")
    print()
    print(" [理論上限] エッジゼロの公平な賭けで4倍を狙う場合の最大成功確率 = 1/4 = 25%")
    print("            同様に20倍 = 1/20 = 5%。手数料分だけこれを下回る。")


if __name__ == "__main__":
    main()
