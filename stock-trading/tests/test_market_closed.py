"""休場日にサイクルを回さないこと"""

import datetime as dt

import pandas as pd
import pytest

import main


def frame(last_day: dt.date) -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(last_day), periods=5)
    return pd.DataFrame({"close": [100.0] * 5}, index=idx)


def jst_today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def test_open_when_latest_bar_is_today():
    closed, latest, today = main.is_market_closed_today({"X": frame(jst_today())})
    assert not closed
    assert latest == today == jst_today()


def test_closed_when_latest_bar_is_stale():
    """祝日は当日の足が無く、直近営業日の足が最新のままになる"""
    stale = jst_today() - dt.timedelta(days=3)
    closed, latest, today = main.is_market_closed_today({"X": frame(stale)})
    assert closed
    assert latest < today


def test_latest_session_uses_newest_across_tickers():
    """銘柄ごとに最終足がずれても、最も新しい取引日を採る"""
    a = frame(jst_today() - dt.timedelta(days=8))
    b = frame(jst_today() - dt.timedelta(days=1))
    newest = max(a.index[-1].date(), b.index[-1].date())
    assert main.latest_session_date({"A": a, "B": b}) == newest
    assert a.index[-1].date() < newest


def test_latest_session_requires_data():
    with pytest.raises(ValueError):
        main.latest_session_date({})


def test_save_universe_uses_latest_session_not_today(tmp_path, monkeypatch):
    """休場日に再選定が走っても as_of は最終取引日で刻む。

    as_of を「今日」にすると、祝日に再選定が走った場合に次回期限が
    非取引日起点でずれていく (2026-11-23 に 1株トラックで発生)。
    """
    import datetime as dt

    from autotrader.screener import screener as sc

    stale = jst_today() - dt.timedelta(days=3)
    path = tmp_path / "universe.json"
    sc.save_universe(str(path), [], as_of=stale.isoformat())

    import json

    saved = json.load(open(path, encoding="utf-8"))
    assert saved["as_of"] == stale.isoformat()
    assert saved["as_of"] != jst_today().isoformat()


def test_screen_stamps_as_of_from_data():
    """screen() が save_universe に最終取引日を渡していること"""
    import datetime as dt
    import inspect

    src = inspect.getsource(main.screen)
    assert "latest_session_date(data)" in src, (
        "screen() は as_of を取得データの最終取引日で刻む必要がある")
    assert "as_of=as_of" in src
