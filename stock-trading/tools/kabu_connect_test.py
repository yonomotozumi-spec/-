"""kabuステーションAPI 疎通確認スクリプト (読み取り専用・発注しない)

あなたのWindows PCで、kabuステーションを起動した状態で実行する:

  python tools/kabu_connect_test.py            # 本番ポート18080 (本番用APIパスワード)
  python tools/kabu_connect_test.py --verify   # 検証ポート18081 (検証用APIパスワード)

APIパスワードは実行時に画面に表示されない形で入力を求める (保存しない)。
確認内容: ①トークン取得 ②銘柄情報 ③時価 ④現物余力 — 発注APIは一切呼ばない。
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.request

TEST_SYMBOL = "9434"  # ソフトバンク (現ユニバース銘柄・高流動)


def req(base: str, method: str, path: str, body: dict | None = None,
        token: str | None = None) -> dict:
    r = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"}
        | ({"X-API-KEY": token} if token else {}),
    )
    with urllib.request.urlopen(r, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="検証ポート18081を使う")
    ap.add_argument("--host", default="localhost")
    args = ap.parse_args()
    port = 18081 if args.verify else 18080
    base = f"http://{args.host}:{port}/kabusapi"
    label = "検証" if args.verify else "本番"
    print(f"接続先: {base} ({label}ポート)")
    import os

    pw = os.environ.get("KABU_API_PASSWORD", "")
    if pw:
        print("APIパスワードは環境変数 KABU_API_PASSWORD から使用")
    else:
        pw = getpass.getpass(f"{label}用APIパスワードを入力 (表示されません): ")

    # 全角文字の混入チェック (IME入力ミスの検出)
    if any(ord(c) > 127 for c in pw):
        print("[警告] パスワードに全角文字が含まれています。IMEを半角英数にして再入力してください")

    ok = 0
    # ① トークン取得
    try:
        r = req(base, "POST", "/token", {"APIPassword": pw})
        if r.get("ResultCode") == 0 and r.get("Token"):
            token = r["Token"]
            print("[OK] 1/4 トークン取得")
            ok += 1
        else:
            print(f"[NG] 1/4 トークン取得: {r}")
            print("     → APIパスワードの誤り、または検証用/本番用の取り違えの可能性")
            sys.exit(1)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = "(詳細なし)"
        print(f"[NG] 1/4 認証エラー: HTTP {e.code} / サーバー応答: {detail}")
        print("     接続自体は成功しています。以下を確認してください:")
        print("     ・入力したのは APIシステム設定の「APIパスワード(本番用)」欄の値か")
        print("       (検証用と取り違えていないか / ログインパスワードや注文パスワードではない)")
        print("     ・パスワード設定後に「OK」→ kabuステーションを再起動したか")
        print("       (設定は次回起動時に適用されます)")
        print("     ・IMEが半角英数になっているか (全角文字の混入)")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[NG] 1/4 接続失敗: {e}")
        print("     → kabuステーションが起動しているか / APIシステム設定で「APIを利用する」が")
        print("       有効か (右上アイコンが緑か) / ポート番号が正しいか を確認してください")
        sys.exit(1)

    # ② 銘柄情報
    try:
        r = req(base, "GET", f"/symbol/{TEST_SYMBOL}@1", token=token)
        name = r.get("SymbolName")
        print(f"[OK] 2/4 銘柄情報: {TEST_SYMBOL} = {name}" if name
              else f"[NG] 2/4 銘柄情報: {r}")
        ok += bool(name)
    except Exception as e:
        print(f"[NG] 2/4 銘柄情報: {e}")

    # ③ 時価
    try:
        r = req(base, "GET", f"/board/{TEST_SYMBOL}@1", token=token)
        px = r.get("CurrentPrice")
        print(f"[OK] 3/4 時価取得: {px}円 ({r.get('CurrentPriceTime', '時刻不明')})" if px is not None
              else f"[警告] 3/4 時価がnull (場中でない、または銘柄登録が必要): {str(r)[:120]}")
        ok += px is not None
    except Exception as e:
        print(f"[NG] 3/4 時価取得: {e}")

    # ④ 現物余力
    try:
        r = req(base, "GET", "/wallet/cash", token=token)
        cash = r.get("StockAccountWallet")
        print(f"[OK] 4/4 現物余力: {cash:,.0f}円" if cash is not None
              else f"[NG] 4/4 現物余力: {r}")
        ok += cash is not None
    except Exception as e:
        print(f"[NG] 4/4 現物余力: {e}")

    print()
    if ok == 4:
        print("✅ 疎通確認 4/4 すべて成功。実弾移行の技術的準備は完了です。")
    elif ok >= 1:
        print(f"△ {ok}/4 成功。時価nullは引け後なら正常なことがあります。他のNGは上のヒントを確認。")
    else:
        print("❌ 疎通確認失敗。")


if __name__ == "__main__":
    main()
