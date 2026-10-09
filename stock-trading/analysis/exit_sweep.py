"""手仕舞いルールの比較検証 — 固定利確 vs トレーリング vs 利確なし

同じ売買シグナル・同じ期間・同じデータで、出口ルールだけを差し替えて
バックテストし、どれが優れているかを実データで判定する。

  python analysis/exit_sweep.py --start 2023-09-01
"""

from __future__ import annotations

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autotrader.backtest.engine import BacktestEngine  # noqa: E402
from autotrader.config import load_config  # noqa: E402
from autotrader.data.market_data import collect_market_data  # noqa: E402

# (表示名, 固定利確, トレーリング幅)
VARIANTS = [
    ("固定利確 +20% (現行)", 0.20, 0.0),
    ("固定利確 +30%", 0.30, 0.0),
    ("固定利確 +50%", 0.50, 0.0),
    ("利確なし (シグナル任せ)", 0.0, 0.0),
    ("トレーリング -8%", 0.0, 0.08),
    ("トレーリング -12%", 0.0, 0.12),
    ("トレーリング -15%", 0.0, 0.15),
    ("固定+30% と トレーリング-12% 併用", 0.30, 0.12),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-09-01")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default="reports/exit-sweep.md")
    args = ap.parse_args()

    base = load_config(args.config)
    import datetime as dt

    since = (dt.date.today() - dt.date.fromisoformat(args.start)).days
    print(f"データ収集中 ({len(base.universe)}銘柄)...")
    data = collect_market_data(base.universe, max(base.data.lookback_days, since + 150),
                               base.data.interval)
    if not data:
        raise SystemExit("データ取得に失敗しました")

    rows = []
    for name, tp, trail in VARIANTS:
        cfg = copy.deepcopy(base)
        cfg.risk.take_profit_pct = tp
        cfg.risk.trailing_stop_pct = trail
        result = BacktestEngine(cfg).run(data, start=args.start)
        m = result.metrics
        # 決済済み取引の勝敗を集計
        sells = [t for t in result.trades if t.side == "SELL"]
        rows.append({
            "name": name,
            "final": result.final_equity,
            "ret": result.final_equity / cfg.initial_capital - 1,
            "annual": m["annual_return"],
            "vol": m["annual_volatility"],
            "sharpe": m["sharpe"],
            "dd": m["max_drawdown"],
            "trades": len(result.trades),
            "sells": len(sells),
        })
        print(f"  {name:32s} 最終 {result.final_equity:>10,.0f}円  "
              f"Sharpe {m['sharpe']:5.2f}  DD {m['max_drawdown']:6.1%}  取引 {len(result.trades)}回")

    best = max(rows, key=lambda r: r["sharpe"])
    lines = [
        "# 手仕舞いルールの比較検証",
        "",
        f"- 対象銘柄: {', '.join(base.universe)}",
        f"- 検証期間: {args.start} 〜 (同一データ・同一シグナルで出口だけ差し替え)",
        f"- 初期資金: {base.initial_capital:,.0f} 円",
        "",
        "| 出口ルール | 最終資産 | 通算 | 年率 | ボラ | Sharpe | 最大DD | 取引 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        mark = " ★" if r["name"] == best["name"] else ""
        lines.append(
            f"| {r['name']}{mark} | {r['final']:,.0f}円 | {r['ret']:+.1%} | "
            f"{r['annual']:+.1%} | {r['vol']:.1%} | **{r['sharpe']:.2f}** | "
            f"{r['dd']:.1%} | {r['trades']}回 |"
        )
    lines += ["", f"★ = Sharpe最良: **{best['name']}** (Sharpe {best['sharpe']:.2f})", ""]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n結果を書き出しました: {args.out}")
    print(f"Sharpe最良: {best['name']} (Sharpe {best['sharpe']:.2f})")


if __name__ == "__main__":
    main()
