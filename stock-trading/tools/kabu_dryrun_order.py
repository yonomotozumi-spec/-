"""発注コードの動作確認 — 検証ポート(18081) / 実際には発注されない

kabuステーションの検証環境は「常に一定の値を返し、実際に発注はされない」ため、
入金前でも・市場が閉まっていても、発注コードの経路を安全に通せる。

  python tools/kabu_dryrun_order.py

検証できること: 認証 → 発注リクエスト構築 → レスポンス解析 → 例外処理
検証できないこと: フィールド値の意味的な正しさ (口座区分・資産区分など)、
                  実際の受付可否・約定。これらは入金後の本番テスト発注で確認する。

前提: kabuステーションの「APIシステム設定」で検証用APIパスワードを設定済みで
      あること。パスワードは実行時に非表示入力する (保存しない)。
"""

from __future__ import annotations

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SYMBOL = "9434.T"
QTY = 100


def main() -> None:
    print("=" * 62)
    print(" 発注ドライラン (検証ポート18081) — 実際の発注は行われません")
    print("=" * 62)
    if not os.environ.get("KABU_API_PASSWORD_VERIFY"):
        os.environ["KABU_API_PASSWORD_VERIFY"] = getpass.getpass(
            "検証用APIパスワード (表示されません): ")
    if not os.environ.get("KABU_ORDER_PASSWORD"):
        os.environ["KABU_ORDER_PASSWORD"] = getpass.getpass(
            "注文パスワード (表示されません): ")

    from autotrader.execution.kabu import PORT_VERIFY, KabuBroker

    try:
        broker = KabuBroker(port=PORT_VERIFY)
    except RuntimeError as e:
        print(f"[NG] 初期化失敗: {e}")
        sys.exit(1)

    # 検証環境は約定明細を返さないため、待ち時間を短縮する
    orig_wait = broker._wait_fill
    broker._wait_fill = lambda oid, tok, ref, **kw: orig_wait(
        oid, tok, ref, retries=1, interval=0.5)

    checks = []
    try:
        fill = broker.execute(SYMBOL, "BUY", QTY, ref_price=240.0)
        print(f"[OK] 発注リクエスト送信・レスポンス解析に成功")
        print(f"     戻り値: {fill.ticker} {fill.side} {fill.quantity}株 @ {fill.price}")
        checks.append(True)
    except Exception as e:
        print(f"[NG] 発注経路でエラー: {type(e).__name__}: {e}")
        checks.append(False)

    # 単元未満のガードが効くか
    try:
        broker.execute(SYMBOL, "BUY", 150, ref_price=240.0)
        print("[NG] 単元未満(150株)が拒否されませんでした")
        checks.append(False)
    except ValueError:
        print("[OK] 単元未満(150株)を正しく拒否")
        checks.append(True)

    print()
    if all(checks):
        print("✅ ドライラン成功。発注コードの経路は正常に動作します。")
        print("   ※フィールド値の妥当性と実際の約定は、入金後の本番テスト発注で確認します。")
    else:
        print("❌ ドライランで問題を検出しました。上のエラーを確認してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
