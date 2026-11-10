import numpy as np

from autotrader.config import ScreenerConfig
from autotrader.screener.screener import (
    Candidate,
    evaluate_candidate,
    load_universe,
    save_universe,
    select_universe,
    universe_age_days,
)
from tests.conftest import make_ohlcv


def make_df(drift: float, seed: int, volume: int = 1_000_000, days: int = 250):
    rng = np.random.default_rng(seed)
    prices = 2000 * np.cumprod(1 + drift + rng.normal(0, 0.01, days))
    df = make_ohlcv(prices)
    df["volume"] = volume
    return df


def cfg(**kw):
    return ScreenerConfig(**{"target_count": 3, "max_per_sector": 1,
                             "min_turnover_jpy": 1e9, **kw})


def test_high_momentum_scores_higher():
    c = cfg()
    up = evaluate_candidate(Candidate("UP", "A"), make_df(0.003, 1), c)
    flat = evaluate_candidate(Candidate("FLAT", "B"), make_df(0.0, 2), c)
    assert up.score > flat.score


def test_low_liquidity_excluded():
    c = cfg()
    # 株価2000円×出来高100株 = 売買代金約20万円/日 → 足切り
    r = evaluate_candidate(Candidate("THIN", "A"), make_df(0.003, 3, volume=100), c)
    assert r.score == float("-inf")
    assert "流動性不足" in r.reason


def test_insufficient_history_excluded():
    c = cfg()
    r = evaluate_candidate(Candidate("NEW", "A"), make_df(0.003, 4, days=100), c)
    assert r.score == float("-inf")


def test_sector_cap_enforced():
    c = cfg(target_count=3, max_per_sector=1)
    results = [
        evaluate_candidate(Candidate(f"T{i}", sector), make_df(0.004 - i * 0.001, i), c)
        for i, sector in enumerate(["半導体", "半導体", "銀行", "商社"])
    ]
    selected = select_universe(results, c)
    sectors = [r.sector for r in selected]
    assert len(selected) == 3
    assert sectors.count("半導体") == 1  # 2銘柄目の半導体はセクター上限で落ちる


def test_target_count_respected():
    c = cfg(target_count=2, max_per_sector=5)
    results = [
        evaluate_candidate(Candidate(f"T{i}", "X"), make_df(0.002, 10 + i), c)
        for i in range(5)
    ]
    assert len(select_universe(results, c)) == 2


def test_save_and_load_universe(tmp_path):
    c = cfg()
    path = str(tmp_path / "universe.json")
    results = [evaluate_candidate(Candidate("UP", "A"), make_df(0.003, 1), c)]
    selected = select_universe(results, c)
    save_universe(path, selected, as_of="2026-08-24")

    loaded = load_universe(path)
    assert loaded["tickers"] == ["UP"]
    assert loaded["as_of"] == "2026-08-24"
    assert universe_age_days(path) >= 0


def test_unit_cost_filter_excludes_expensive_stocks():
    # 単元コスト上限37.5万: 株価2000円(単元20万)は通過、株価13000円(単元130万)は除外
    c = cfg(max_unit_cost_jpy=375_000)
    cheap = evaluate_candidate(Candidate("CHEAP", "A"), make_df(0.003, 1), c)
    exp_df = make_df(0.003, 1)
    for col in ("open", "high", "low", "close", "bb_upper", "bb_lower",
                "sma_short", "sma_long", "atr"):
        exp_df[col] = exp_df[col] * 6.5
    expensive = evaluate_candidate(Candidate("EXP", "A"), exp_df, c)
    assert cheap.score != float("-inf")
    assert expensive.score == float("-inf")
    assert "単元コスト超過" in expensive.reason


def test_unit_cost_filter_disabled_by_default():
    c = cfg()  # max_unit_cost_jpy=0
    exp_df = make_df(0.003, 1)
    r = evaluate_candidate(Candidate("EXP", "A"), exp_df, c)
    assert r.score != float("-inf")
