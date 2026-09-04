"""銘柄スクリーニング: 候補プールから売買ユニバースを自動選定する

選定ロジック (月次想定):
  1. 流動性フィルタ: 60日平均売買代金が下限以上 (約定コスト・スリッページ対策)
  2. データ充足フィルタ: モメンタム計算に必要な履歴があること
  3. スコアリング: リスク調整後モメンタム (120日リターン / 年率ボラ) + トレンド加点
  4. セクター分散: 同一セクターの採用数に上限を設けて上位から採用
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import asdict, dataclass

import pandas as pd
import yaml

from ..config import ScreenerConfig


@dataclass
class Candidate:
    ticker: str
    sector: str


@dataclass
class ScreenResult:
    ticker: str
    sector: str
    score: float
    momentum_120d: float
    volatility: float
    turnover_avg_jpy: float
    selected: bool
    reason: str


def load_candidates(path: str) -> list[Candidate]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return [Candidate(str(c["ticker"]), str(c["sector"])) for c in raw.get("candidates", [])]


def evaluate_candidate(cand: Candidate, df: pd.DataFrame, cfg: ScreenerConfig) -> ScreenResult:
    """指標付き日足データから候補1銘柄を評価する (選定はまだしない)"""
    base = ScreenResult(cand.ticker, cand.sector, float("-inf"), 0.0, 0.0, 0.0, False, "")

    if len(df) < 140:
        base.reason = f"履歴不足 ({len(df)}日)"
        return base

    close = df["close"]
    turnover = float((close * df["volume"]).tail(60).mean())
    base.turnover_avg_jpy = turnover
    if turnover < cfg.min_turnover_jpy:
        base.reason = f"流動性不足 (売買代金 {turnover / 1e8:.1f}億円/日)"
        return base

    # 単元コストフィルタ: 100株単元が予算内で買えない銘柄を除外 (単元株モード用)
    if cfg.max_unit_cost_jpy > 0:
        unit_cost = float(close.iloc[-1]) * 100
        if unit_cost > cfg.max_unit_cost_jpy:
            base.reason = f"単元コスト超過 ({unit_cost / 1e4:,.0f}万円/単元)"
            return base

    mom = float(close.iloc[-1] / close.iloc[-120] - 1)
    vol = float(df["ret_1d"].tail(120).std() * (252**0.5))
    base.momentum_120d = mom
    base.volatility = vol
    if vol <= 0 or pd.isna(vol):
        base.reason = "ボラティリティ計算不可"
        return base

    score = mom / vol
    # 中期トレンドが上向きなら加点 (モメンタムの持続性)
    row = df.iloc[-1]
    if not pd.isna(row["sma_long"]) and row["sma_short"] > row["sma_long"]:
        score += 0.1
    base.score = score
    base.reason = f"mom120 {mom:+.1%} / vol {vol:.0%} / 代金 {turnover / 1e8:.0f}億円"
    return base


def select_universe(
    results: list[ScreenResult], cfg: ScreenerConfig
) -> list[ScreenResult]:
    """スコア降順にセクター上限を守りながら target_count 銘柄を選ぶ"""
    eligible = sorted(
        (r for r in results if r.score != float("-inf")),
        key=lambda r: r.score,
        reverse=True,
    )
    sector_count: dict[str, int] = {}
    selected: list[ScreenResult] = []
    for r in eligible:
        if len(selected) >= cfg.target_count:
            break
        if sector_count.get(r.sector, 0) >= cfg.max_per_sector:
            r.reason += " / セクター上限で見送り"
            continue
        r.selected = True
        sector_count[r.sector] = sector_count.get(r.sector, 0) + 1
        selected.append(r)
    return selected


def save_universe(path: str, selected: list[ScreenResult], as_of: str | None = None) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "as_of": as_of or dt.date.today().isoformat(),
        "tickers": [r.ticker for r in selected],
        "details": [asdict(r) for r in selected],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_universe(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def universe_age_days(path: str) -> int | None:
    data = load_universe(path)
    if not data:
        return None
    return (dt.date.today() - dt.date.fromisoformat(data["as_of"])).days
