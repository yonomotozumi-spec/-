"""株式自動取引システム CLI

使い方:
  python main.py advise                     売買指示の生成のみ (発注なし)
  python main.py run                        自動売買サイクルを1回実行 (ペーパートレード)
  python main.py backtest --start 2023-01-01
  python main.py report                     ポートフォリオ・リスクレポート
"""

from __future__ import annotations

import argparse
import json

from autotrader.backtest.engine import BacktestEngine
from autotrader.config import load_config
from autotrader.data.market_data import collect_market_data
from autotrader.manager import CycleResult, TradingManager


def print_cycle(result: CycleResult, executed: bool) -> None:
    mode = "執行済み (ペーパー)" if executed else "指示のみ"
    print(f"\n=== 売買指示 {result.date} [{mode}] ===")
    if not result.instructions:
        print("  本日のアクションはありません (全銘柄HOLD)")
    for inst in result.instructions:
        status = "✓執行" if inst.executed else ("✗未執行" if executed else "提案")
        print(
            f"  [{status}] {inst.action:4s} {inst.ticker:8s} "
            f"{inst.quantity:>6,}株 @ {inst.price:,.1f}  score={inst.score:+.2f}"
        )
        print(f"          理由: {inst.reason}")
    for w in result.warnings:
        print(f"  [警告] {w}")
    print_summary(result.portfolio_summary)


def print_summary(s: dict) -> None:
    if not s:
        return
    print("\n=== ポートフォリオ現況 ===")
    print(f"  総資産:     {s['equity']:>14,.0f} 円 (累積損益 {s['total_return_pct']:+.2f}%)")
    print(f"  現金:       {s['cash']:>14,.0f} 円")
    print(f"  株式比率:   {s['gross_exposure_pct']:.1f}%")
    if s.get("holdings"):
        print("  保有銘柄:")
        for h in s["holdings"]:
            print(
                f"    {h['ticker']:8s} {h['quantity']:>6,}株  取得 {h['avg_cost']:,.1f} → "
                f"現在 {h['price']:,.1f}  損益 {h['pnl_pct']:+.2f}%  配分 {h['weight_pct']}%"
            )
    if s.get("risk"):
        r = s["risk"]
        print("  リスク指標 (保有ベース・年率):")
        print(f"    期待リターン {r.get('annual_return', 0):+.1%} / ボラ {r.get('annual_volatility', 0):.1%}"
              f" / シャープ {r.get('sharpe', 0):.2f} / ソルティノ {r.get('sortino', 0):.2f}")
        print(f"    最大DD {r.get('max_drawdown', 0):.1%} / 日次VaR95 {r.get('var_95', 0):.2%}"
              f" / CVaR95 {r.get('cvar_95', 0):.2%}")
        if not s.get("var_within_limit", True):
            print("    ⚠ ポートフォリオVaRが許容上限を超えています。エクスポージャー削減を検討してください")


def main() -> None:
    parser = argparse.ArgumentParser(description="株式自動取引システム")
    parser.add_argument("command", choices=["advise", "run", "backtest", "report"])
    parser.add_argument("--config", default=None, help="設定ファイルのパス")
    parser.add_argument("--start", default=None, help="バックテスト開始日 (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    args = parser.parse_args()

    cfg = load_config(args.config)
    print(f"マーケットデータ収集中... ({len(cfg.universe)}銘柄)")
    data = collect_market_data(cfg.universe, cfg.data.lookback_days, cfg.data.interval)
    if not data:
        raise SystemExit("エラー: 全銘柄のデータ取得に失敗しました。ネットワークを確認してください")

    if args.command in ("advise", "run"):
        manager = TradingManager(cfg)
        result = manager.run_cycle(data, execute=(args.command == "run"))
        if args.json:
            print(json.dumps(
                {
                    "date": result.date,
                    "instructions": [vars(i) for i in result.instructions],
                    "summary": result.portfolio_summary,
                    "warnings": result.warnings,
                },
                ensure_ascii=False, indent=2,
            ))
        else:
            print_cycle(result, executed=(args.command == "run"))

    elif args.command == "report":
        manager = TradingManager(cfg)
        print_summary(manager.report(data))

    elif args.command == "backtest":
        engine = BacktestEngine(cfg)
        result = engine.run(data, start=args.start)
        print(f"\n=== バックテスト結果 ({result.equity_curve.index[0].date()} 〜 "
              f"{result.equity_curve.index[-1].date()}) ===")
        print(f"  初期資金:   {cfg.initial_capital:>14,.0f} 円")
        print(f"  最終資産:   {result.final_equity:>14,.0f} 円 "
              f"({(result.final_equity / cfg.initial_capital - 1) * 100:+.2f}%)")
        m = result.metrics
        print(f"  年率リターン {m['annual_return']:+.1%} / ボラ {m['annual_volatility']:.1%} / "
              f"シャープ {m['sharpe']:.2f} / ソルティノ {m['sortino']:.2f}")
        print(f"  最大DD {m['max_drawdown']:.1%} / 日次VaR95 {m['var_95']:.2%} / "
              f"CVaR95 {m['cvar_95']:.2%}")
        print(f"  取引回数:   {len(result.trades)} 回")


if __name__ == "__main__":
    main()
