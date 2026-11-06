"""保有・決済銘柄の価格系列を監査する。

`yfinance` は `auto_adjust=True` で配当・分割を遡って反映するため、過去の
終値が後から書き換わる。一方 `portfolio.json` の `avg_cost` は約定当時の
調整済み価格をそのまま保存しているので、権利落ちを挟むと「保有中に
取得単価だけが据え置かれ、価格系列は下方修正される」というズレが生じ、
実際には下がっていない銘柄が損切り判定に掛かることがある。

このスクリプトは実データを取得できる環境 (GitHub Actions) で動かし、
直近の終値・日次変化率・配当・分割を並べて、急落が実体か調整由来かを
切り分けるために使う。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys


def audit(tickers: list[str], days: int) -> str:
    import pandas as pd
    import yfinance as yf

    end = dt.date.today() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=days)
    out: list[str] = ["# 価格系列の監査", ""]
    out.append(f"取得期間 {start} 〜 {end} / auto_adjust=True と False を併記")
    out.append("")
    for tk in tickers:
        out.append(f"## {tk}")
        t = yf.Ticker(tk)
        try:
            adj = t.history(start=start, end=end, interval="1d", auto_adjust=True)
            raw = t.history(start=start, end=end, interval="1d", auto_adjust=False)
        except Exception as e:  # 1銘柄の失敗で監査全体を落とさない
            out.append(f"データ取得に失敗: {type(e).__name__}")
            out.append("")
            continue
        if adj.empty:
            out.append("データ取得に失敗")
            out.append("")
            continue
        rows = ["| 日付 | 調整後終値 | 前日比 | 無調整終値 | 配当 | 分割 |",
                "|---|---|---|---|---|---|"]
        prev = None
        for idx, r in adj.iterrows():
            d = idx.date()
            chg = "" if prev is None else f"{(r['Close']/prev - 1) * 100:+.2f}%"
            prev = r["Close"]
            rr = raw.loc[raw.index.date == d] if not raw.empty else None
            rawc = f"{rr['Close'].iloc[0]:,.2f}" if rr is not None and len(rr) else "-"
            div = r.get("Dividends", 0.0) or 0.0
            spl = r.get("Stock Splits", 0.0) or 0.0
            rows.append(f"| {d} | {r['Close']:,.2f} | {chg} | {rawc} | "
                        f"{div:,.2f} | {spl:g} |")
        out.extend(rows)
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True,
                    help="カンマ区切りの銘柄コード (例 2914.T,9101.T)")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--out")
    a = ap.parse_args()
    md = audit([t.strip() for t in a.tickers.split(",") if t.strip()], a.days)
    print(md)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
