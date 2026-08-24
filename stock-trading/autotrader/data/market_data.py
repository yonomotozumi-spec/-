"""マーケットデータの収集とテクニカル指標の計算

yfinance で日足データを取得する。テスト時は fetch を経由せず
add_indicators() に合成データを渡せる構造にしている。
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


def fetch_history(ticker: str, lookback_days: int = 400, interval: str = "1d") -> pd.DataFrame:
    """yfinance から OHLCV 日足を取得して指標付きで返す"""
    import yfinance as yf

    end = dt.date.today() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=int(lookback_days * 1.6))  # 休日分を多めに取る
    df = yf.Ticker(ticker).history(
        start=start.isoformat(), end=end.isoformat(), interval=interval, auto_adjust=True
    )
    if df.empty:
        raise RuntimeError(f"{ticker}: 価格データを取得できませんでした")
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return add_indicators(df)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """テクニカル指標を追加する。df は open/high/low/close/volume を持つ日足"""
    out = df.copy()
    close = out["close"]

    out["sma_short"] = close.rolling(20).mean()
    out["sma_long"] = close.rolling(60).mean()
    out["ret_1d"] = close.pct_change()
    out["ret_20d"] = close.pct_change(20)

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = 100 - 100 / (1 + rs)

    # ボリンジャーバンド(20, 2σ)
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    out["bb_upper"] = mid + 2 * std
    out["bb_lower"] = mid - 2 * std
    out["bb_z"] = (close - mid) / std.replace(0, np.nan)

    # ATR(14) — 損切り幅やボラ推定に使用
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - close.shift()).abs(),
            (out["low"] - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(14).mean()

    # 年率ボラティリティ(60日)
    out["volatility"] = out["ret_1d"].rolling(60).std() * np.sqrt(252)
    return out


def collect_market_data(
    tickers: list[str], lookback_days: int = 400, interval: str = "1d"
) -> dict[str, pd.DataFrame]:
    """複数銘柄のデータを収集する。取得失敗銘柄はスキップして警告する"""
    data: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            data[t] = fetch_history(t, lookback_days, interval)
        except Exception as e:  # ネットワーク断・上場廃止などは運用を止めない
            print(f"[warn] {t}: データ取得に失敗しました ({e})")
    return data
