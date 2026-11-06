import numpy as np
import pandas as pd

from autotrader.risk.metrics import (
    annualized_return,
    annualized_volatility,
    historical_cvar,
    historical_var,
    max_drawdown,
    sharpe_ratio,
    summarize,
)


def test_annualized_return_positive():
    # 毎日+0.1%なら年率約28.6%
    r = pd.Series([0.001] * 252)
    assert abs(annualized_return(r) - (1.001**252 - 1)) < 1e-9


def test_volatility_zero_for_constant():
    r = pd.Series([0.001] * 100)
    assert annualized_volatility(r) < 1e-12


def test_sharpe_sign():
    rng = np.random.default_rng(0)
    up = pd.Series(rng.normal(0.002, 0.01, 500))
    down = pd.Series(rng.normal(-0.002, 0.01, 500))
    assert sharpe_ratio(up) > 0
    assert sharpe_ratio(down) < 0


def test_max_drawdown():
    equity = pd.Series([100, 120, 90, 110, 80])
    # ピーク120から80まで -33.3%
    assert abs(max_drawdown(equity) - (80 / 120 - 1)) < 1e-9


def test_var_cvar_relationship():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0, 0.02, 1000))
    var = historical_var(r)
    cvar = historical_cvar(r)
    assert var > 0
    assert cvar >= var  # CVaRは常にVaR以上


def test_summarize_keys():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.001, 0.01, 300))
    s = summarize(r)
    for key in ["annual_return", "annual_volatility", "sharpe", "sortino",
                "max_drawdown", "var_95", "cvar_95"]:
        assert key in s
