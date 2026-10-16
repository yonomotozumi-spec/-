"""テスト共通フィクスチャ: 合成価格データ (ネットワーク不要)"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autotrader.data.market_data import add_indicators  # noqa: E402


def make_ohlcv(prices: np.ndarray, start: str = "2023-01-02") -> pd.DataFrame:
    """終値系列から OHLCV 日足を合成し指標を付与する"""
    idx = pd.bdate_range(start, periods=len(prices))
    close = pd.Series(prices, index=idx)
    df = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        }
    )
    return add_indicators(df)


@pytest.fixture
def uptrend_df():
    """一貫した上昇トレンド (+0.4%/日 + ノイズ)"""
    rng = np.random.default_rng(42)
    prices = 1000 * np.cumprod(1 + 0.004 + rng.normal(0, 0.005, 250))
    return make_ohlcv(prices)


@pytest.fixture
def downtrend_df():
    """一貫した下降トレンド"""
    rng = np.random.default_rng(42)
    prices = 1000 * np.cumprod(1 - 0.004 + rng.normal(0, 0.005, 250))
    return make_ohlcv(prices)


@pytest.fixture
def flat_df():
    """横ばい"""
    rng = np.random.default_rng(7)
    prices = 1000 * np.cumprod(1 + rng.normal(0, 0.002, 250))
    return make_ohlcv(prices)
