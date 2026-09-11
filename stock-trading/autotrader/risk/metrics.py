"""リスク・リターン指標の計算"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def annualized_return(returns: pd.Series) -> float:
    """日次リターン系列から年率リターン(幾何平均ベース)を計算"""
    r = returns.dropna()
    if len(r) == 0:
        return 0.0
    total = float((1 + r).prod())
    if total <= 0:
        return -1.0
    return total ** (TRADING_DAYS / len(r)) - 1


def annualized_volatility(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    return float(r.std() * np.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    vol = annualized_volatility(returns)
    if vol == 0:
        return 0.0
    return (annualized_return(returns) - risk_free_rate) / vol


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    r = returns.dropna()
    downside = r[r < 0]
    if len(downside) < 2:
        return 0.0
    dd_vol = float(downside.std() * np.sqrt(TRADING_DAYS))
    if dd_vol == 0:
        return 0.0
    return (annualized_return(r) - risk_free_rate) / dd_vol


def max_drawdown(equity: pd.Series) -> float:
    """資産曲線から最大ドローダウン(負の値)を計算"""
    e = equity.dropna()
    if len(e) == 0:
        return 0.0
    peak = e.cummax()
    return float(((e - peak) / peak).min())


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """ヒストリカルVaR。日次リターンの下位(1-confidence)分位を正の損失率で返す"""
    r = returns.dropna()
    if len(r) < 20:
        return 0.0
    return float(max(0.0, -np.percentile(r, (1 - confidence) * 100)))


def historical_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """CVaR (期待ショートフォール)。VaR超過損失の平均を正の損失率で返す"""
    r = returns.dropna()
    if len(r) < 20:
        return 0.0
    threshold = np.percentile(r, (1 - confidence) * 100)
    tail = r[r <= threshold]
    if len(tail) == 0:
        return 0.0
    return float(max(0.0, -tail.mean()))


def summarize(returns: pd.Series, risk_free_rate: float = 0.0) -> dict[str, float]:
    """リターン系列の主要指標をまとめて計算する"""
    equity = (1 + returns.fillna(0)).cumprod()
    return {
        "annual_return": annualized_return(returns),
        "annual_volatility": annualized_volatility(returns),
        "sharpe": sharpe_ratio(returns, risk_free_rate),
        "sortino": sortino_ratio(returns, risk_free_rate),
        "max_drawdown": max_drawdown(equity),
        "var_95": historical_var(returns),
        "cvar_95": historical_cvar(returns),
    }
