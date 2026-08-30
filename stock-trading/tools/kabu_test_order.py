"""実弾テスト発注スクリプト — ソフトバンク(9434) 1単元の買い→売り往復

発注→約定→約定照会の全経路を最小金額 (約2.4万円) で実弾検証する。
入金完了後、ザラ場中 (平日9:00〜15:25頃) にkabuステーション起動状態で実行する:

  python tools/kabu_test_order.py

安全装置:
  - 環境変数 KABU_CONFIRM_LIVE=yes が必要
  - 実行時に「test」と手入力しないと発注しない
  - 対象は 9434 (ソフトバンク) 100株 固定・成行のみ
  - 買い約定の確認後、続けて売り(往復)するか選択できる
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMBOL = "9434.T"
QTY = 100


def main() -> None:
    if os.environ.get("KABU_CONFIRM_LIVE") != "yes":
        print("環境変数 KABU_CONFIRM_LIVE=yes を設定してから実行してください (安全装置)")
        print('PowerShell (このセッション限り): $env:KABU_CONFIRM_LIVE="yes"')
        sys.exit(1)

    from autotrader.execution.kabu import KabuBroker

    broker = KabuBroker()
    print("=" * 60)
    print(f" 実弾テスト発注: {SYMBOL} {QTY}株 成行買い (約2.4万円)")
    print(" ※これは仮想売買ではありません。実際に注文が執行されます")
    print("=" * 60)
    if input("実行するには test と入力: ").strip() != "test":
        print("中止しました")
        return

    print("買い注文を発注中...")
    fill = broker.execute(SYMBOL, "BUY", QTY, ref_price=240.0)
    print(f"✅ 買い約定: {fill.quantity}株 @ {fill.price:,.1f}円 (約 {fill.quantity * fill.price:,.0f}円)")

    if input("続けて売却し往復テストを完了しますか? (yes/no): ").strip().lower() == "yes":
        print("売り注文を発注中...")
        fill2 = broker.execute(SYMBOL, "SELL", QTY, ref_price=fill.price)
        pnl = (fill2.price - fill.price) * QTY
        print(f"✅ 売り約定: {fill2.quantity}株 @ {fill2.price:,.1f}円 (往復損益 {pnl:+,.0f}円)")
        print("往復テスト完了。発注経路の実弾検証に成功しました。")
    else:
        print(f"{SYMBOL} {QTY}株を保有したまま終了します (ユニバース採用銘柄のため運用に組込可)")


if __name__ == "__main__":
    main()
