"""三菱UFJ eスマート証券 kabuステーションAPI アダプタ

ユーザーのWindows PC上で起動中のkabuステーションへ localhost REST で接続する。
発注は現物・単元株・SOR(最良執行)のみサポート。SOR指定は2つの理由で必須:
  ・2026年2月以降、市場コード「1(東証)」直接指定の新規発注が不可
  ・2026年5月18日以降、SOR注文が国内株式手数料無料化の条件

既知の制約 (実弾移行前に対応が必要):
  既定の寄成(前場)は翌営業日の寄付まで約定しないため、_wait_fill は
  タイムアウトして参照価格を返す。正しい約定単価は翌日サイクルの冒頭で
  /orders から取得して補正する必要がある (照合処理は未実装)。

必要な環境変数:
  KABU_API_PASSWORD         本番用APIパスワード (port=18080)
  KABU_API_PASSWORD_VERIFY  検証用APIパスワード (port=18081)
  KABU_ORDER_PASSWORD       注文パスワード
  KABU_CONFIRM_LIVE         "yes" でないと本番発注を拒否する安全装置
                            (検証ポートは実発注されないため不要)

※ 実機での発注検証は未実施。tools/kabu_dryrun_order.py (検証ポート) で
   コード経路を確認し、入金後に tools/kabu_test_order.py で1単元の
   本番テスト発注を行うこと。
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

from .broker import Broker, Fill

EXCHANGE_SOR = 9          # SOR (最良執行)
SECURITY_TYPE_STOCK = 1
CASH_MARGIN_SPOT = 1      # 現物
DELIV_TYPE_DEPOSIT = 2    # お預り金
FUND_TYPE_CASH = "AA"     # 信用代用 (現金)
ACCOUNT_TYPE_TOKUTEI = 4  # 特定口座
ORDER_TYPE_MARKET = 10          # 成行 (即時執行・ザラ場用)
ORDER_TYPE_OPENING_MARKET = 13  # 寄成（前場）翌営業日の寄付で約定

PORT_LIVE = 18080    # 本番用: 実際に発注される
PORT_VERIFY = 18081  # 検証用: 常に一定の値を返し、実際には発注されない


class KabuBroker(Broker):
    def __init__(self, host: str = "localhost", port: int = PORT_LIVE,
                 max_orders_per_day: int = 0,
                 order_type: int = ORDER_TYPE_OPENING_MARKET):
        self.base = f"http://{host}:{port}/kabusapi"
        # 検証ポートは実際には発注されないため、環境変数の安全装置を要求しない
        self.verify_mode = port == PORT_VERIFY
        pw_env = "KABU_API_PASSWORD_VERIFY" if self.verify_mode else "KABU_API_PASSWORD"
        self.api_password = os.environ.get(pw_env, "")
        self.order_password = os.environ.get("KABU_ORDER_PASSWORD", "")
        if not self.api_password or not self.order_password:
            raise RuntimeError(
                f"環境変数 {pw_env} / KABU_ORDER_PASSWORD を設定してください")
        if not self.verify_mode and os.environ.get("KABU_CONFIRM_LIVE") != "yes":
            raise RuntimeError(
                "実発注には環境変数 KABU_CONFIRM_LIVE=yes が必要です (安全装置)")
        self.max_orders_per_day = max_orders_per_day  # 0=無制限
        # 既定は寄成(前場): 日次サイクルは引け後に走るため、翌営業日の寄付で
        # 東証の板が最も厚いタイミングに約定させる。成行のままだと夜間PTSに
        # 流れて薄い板で不利約定するリスクがある。ザラ場での即時執行が必要な
        # 場合のみ ORDER_TYPE_MARKET を渡す。
        self.order_type = order_type
        self._orders_today = 0
        self._token: str | None = None

    # ---- HTTP (テストでモックする単位) -----------------------------------
    def _request(self, method: str, path: str, body: dict | None = None,
                 token: str | None = None) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"}
            | ({"X-API-KEY": token} if token else {}),
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _get_token(self) -> str:
        if not self._token:
            r = self._request("POST", "/token", {"APIPassword": self.api_password})
            if r.get("ResultCode") != 0 or "Token" not in r:
                raise RuntimeError(f"トークン取得失敗: {r}")
            self._token = r["Token"]
        return self._token

    # ---- Broker インターフェース ------------------------------------------
    def execute(self, ticker: str, side: str, quantity: int, ref_price: float) -> Fill:
        if quantity <= 0 or quantity % 100 != 0:
            raise ValueError(f"{ticker}: 単元(100株)単位でのみ発注可能 ({quantity}株)")
        if self.max_orders_per_day and self._orders_today >= self.max_orders_per_day:
            raise ValueError("本日の発注上限に達しました (試運転リミッター)")

        symbol = ticker.replace(".T", "")
        token = self._get_token()
        order = {
            "Password": self.order_password,
            "Symbol": symbol,
            "Exchange": EXCHANGE_SOR,
            "SecurityType": SECURITY_TYPE_STOCK,
            "Side": "2" if side == "BUY" else "1",
            "CashMargin": CASH_MARGIN_SPOT,
            "DelivType": DELIV_TYPE_DEPOSIT if side == "BUY" else 0,
            # 現物買の資産区分: AA=信用代用(信用口座あり) / 02=保護(現物口座のみ)
            "FundType": os.environ.get("KABU_FUND_TYPE", FUND_TYPE_CASH)
            if side == "BUY" else "  ",
            "AccountType": ACCOUNT_TYPE_TOKUTEI,
            "Qty": quantity,
            "FrontOrderType": self.order_type,
            "Price": 0,
            "ExpireDay": 0,
        }
        r = self._request("POST", "/sendorder", order, token)
        if r.get("Result") != 0:
            raise ValueError(f"{ticker}: 発注エラー {r}")
        self._orders_today += 1
        order_id = r.get("OrderId", "")

        price, commission = self._wait_fill(order_id, token, ref_price)
        return Fill(ticker, side, quantity, price, commission)

    def _wait_fill(self, order_id: str, token: str, ref_price: float,
                   retries: int = 6, interval: float = 2.0) -> tuple[float, float]:
        """約定照会をポーリングし約定単価を取る。

        State=5(終了) は全約定のほか取消・失効・期限切れ・発注エラーも含むため、
        約定明細 (RecType=8) の有無で判別する。タイムアウト時のみ参照価格で近似。
        """
        for _ in range(retries):
            try:
                orders = self._request("GET", f"/orders?id={order_id}", token=token)
                for o in orders if isinstance(orders, list) else []:
                    if o.get("ID") != order_id or o.get("State") != 5:
                        continue
                    fills = [d for d in o.get("Details", []) if d.get("RecType") == 8]
                    if fills:
                        qty = sum(d["Qty"] for d in fills)
                        avg = sum(d["Price"] * d["Qty"] for d in fills) / qty
                        return round(avg, 2), 0.0  # 手数料は月次明細で照合
                    raise ValueError(
                        f"注文 {order_id} は約定せずに終了しました (取消/失効/エラー)")
            except ValueError:
                raise
            except Exception:
                pass
            time.sleep(interval)
        return round(ref_price, 2), 0.0
