"""ユニバース比較 — 同じ戦略を日本株・米国株それぞれに適用して比較する

目的は「米国株を追加する価値があるか」の判断材料を作ること。

重要な制約:
  現在の Portfolio は通貨の概念を持たないため、円建て銘柄とドル建て銘柄を
  同一ポートフォリオで扱うと、1株200円と200ドルが同じ価格として扱われ
  結果が無意味になる。したがって混合ポートフォリオは測定しない。
  代わりに「単一通貨のポートフォリオを2本」走らせ、
    1. 米国株でも同じエッジが出るか (戦略の汎用性)
    2. 2本の資産曲線の相関 (分散効果の大きさ)
  を測る。この2点が多通貨対応を実装する価値を決める。

  python analysis/universe_compare.py --start 2023-09-01
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autotrader.backtest.engine import BacktestEngine  # noqa: E402
from autotrader.config import load_config  # noqa: E402
from autotrader.data.market_data import collect_market_data  # noqa: E402

# 日本株: 現行 planLive のユニバース選定元から代表8銘柄 (セクター分散)
JP = ["7203.T", "6758.T", "6501.T", "9101.T", "2914.T", "9434.T", "8306.T", "4005.T"]

# 米国株: S&P100級の大型株からセクターを分散させた8銘柄
# 単元の概念がなく1株単位で買えるため、円建てトラックの単元制約は生じない
US = ["AAPL", "MSFT", "JNJ", "JPM", "XOM", "PG", "CAT", "VZ"]


def metrics(curve: pd.Series, rf: float = 0.001) -> dict:
    r = curve.pct_change().dropna()
    if len(r) < 2 or r.std() == 0:
        return {}
    dn = r[r < 0]
    return dict(
        total=curve.iloc[-1] / curve.iloc[0] - 1,
        ann=r.mean() * 252,
        vol=r.std() * np.sqrt(252),
        sharpe=(r.mean() * 252 - rf) / (r.std() * np.sqrt(252)),
        sortino=((r.mean() * 252 - rf) / (dn.std() * np.sqrt(252))
                 if len(dn) > 1 and dn.std() > 0 else float("nan")),
        dd=(curve / curve.cummax() - 1).min(),
    )


def run(base, tickers, lookback, start):
    cfg = copy.deepcopy(base)
    cfg.universe = list(tickers)
    cfg.screener.enabled = False
    cfg.execution.lot_size = 1   # 米国株に単元はなく、比較のため日本株側も1株に揃える
    data = collect_market_data(tickers, lookback, cfg.data.interval)
    if not data:
        raise SystemExit("データ取得に失敗しました")
    res = BacktestEngine(cfg).run(data, start=start)
    return res, sorted(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-09-01")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default="reports/universe-compare.md")
    args = ap.parse_args()

    base = load_config(args.config)
    since = (dt.date.today() - dt.date.fromisoformat(args.start)).days
    lookback = max(base.data.lookback_days, since + 150)

    results = {}
    for name, tickers in (("日本株", JP), ("米国株", US)):
        print(f"{name} {len(tickers)}銘柄を収集・検証中...")
        res, got = run(base, tickers, lookback, args.start)
        results[name] = res
        print(f"  取得できた銘柄: {len(got)} / {len(tickers)}")

    lines = [
        f"# ユニバース比較 (開始 {args.start} / 初期資金 {base.initial_capital:,.0f} / 1株単位)",
        "",
        "同一の戦略・リスク管理を、日本株と米国株にそれぞれ単一通貨で適用した結果。",
        "**混合ポートフォリオは測定していない** (Portfolio が通貨を持たないため、",
        "円とドルを混ぜると価格が同一視され結果が無意味になる)。",
        "",
        "| ユニバース | 通算 | 年率 | ボラ | Sharpe | Sortino | 最大DD |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, res in results.items():
        m = metrics(res.equity_curve)
        lines.append(
            f"| {name} | {m['total']:+.1%} | {m['ann']:+.1%} | {m['vol']:.1%} "
            f"| {m['sharpe']:.2f} | {m['sortino']:.2f} | {m['dd']:.1%} |"
        )

    # 分散効果: 2本の日次リターンの相関と、50:50で持った場合の指標
    a = results["日本株"].equity_curve.pct_change().dropna()
    b = results["米国株"].equity_curve.pct_change().dropna()
    joined = pd.concat([a.rename("jp"), b.rename("us")], axis=1).dropna()
    corr = joined["jp"].corr(joined["us"])
    blend = (1 + joined.mean(axis=1)).cumprod() * base.initial_capital
    bm = metrics(blend)
    lines += [
        f"| **50:50 合成** | {bm['total']:+.1%} | {bm['ann']:+.1%} | {bm['vol']:.1%} "
        f"| **{bm['sharpe']:.2f}** | {bm['sortino']:.2f} | {bm['dd']:.1%} |",
        "",
        "## 分散効果",
        "",
        f"- 日次リターンの相関: **{corr:+.2f}** (重複日数 {len(joined)}日)",
        "- 相関が低いほど合成のボラが下がり Sharpe が改善する。"
        "合成行は為替変動・為替手数料・売買手数料を含まない上限値であることに注意",
        "",
        "## この数字の限界",
        "",
        "- 銘柄は固定の代表8銘柄で、実運用のスクリーニング(月次入替)を通していない",
        "- 米国株側に為替(USD/JPY)の損益と為替スプレッド(往復 約0.2〜0.5%)が含まれていない",
        "- 米国株の売買手数料(約定代金の0.495%・上限22ドル)も含まれていない",
        "- したがって米国株・合成の数値は**実際より有利に出ている**",
    ]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n書き出し: {args.out}")


if __name__ == "__main__":
    main()
