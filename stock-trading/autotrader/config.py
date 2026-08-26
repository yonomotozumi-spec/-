"""設定ファイルの読み込み"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.yaml"
)


@dataclass
class RiskConfig:
    max_position_weight: float = 0.20
    max_gross_exposure: float = 0.90
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.20
    max_daily_var_pct: float = 0.03
    risk_free_rate: float = 0.001


@dataclass
class StrategyConfig:
    momentum_weight: float = 0.6
    mean_reversion_weight: float = 0.4
    buy_threshold: float = 0.35
    sell_threshold: float = -0.35


@dataclass
class ExecutionConfig:
    mode: str = "paper"
    commission_pct: float = 0.0005
    slippage_pct: float = 0.0005
    # 売買単位。100=単元株のみ / 1=単元未満株 (SBI S株・楽天かぶミニ等) 前提
    lot_size: int = 100


@dataclass
class DataConfig:
    lookback_days: int = 400
    interval: str = "1d"


@dataclass
class ScreenerConfig:
    enabled: bool = False
    candidates_file: str = "config/candidates.yaml"
    target_count: int = 8              # 選定する銘柄数
    min_turnover_jpy: float = 1.0e9    # 60日平均売買代金の下限 (円)
    max_per_sector: int = 2            # 同一セクターの採用上限
    refresh_days: int = 30             # ユニバースの再選定間隔 (日)
    universe_file: str = "state/universe.json"
    # 単元(100株)の取得コスト上限 (円)。0=無効。
    # 単元株モード (execution.lot_size>=100) では未設定時に
    # 「初期資金 × 1銘柄配分上限」が自動適用される
    max_unit_cost_jpy: float = 0


@dataclass
class Config:
    universe: list[str] = field(default_factory=list)
    initial_capital: float = 3_000_000
    data: DataConfig = field(default_factory=DataConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    screener: ScreenerConfig = field(default_factory=ScreenerConfig)
    state_file: str = "state/portfolio.json"


def load_config(path: str | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config(
        universe=list(raw.get("universe", [])),
        initial_capital=float(raw.get("initial_capital", 3_000_000)),
        data=DataConfig(**raw.get("data", {})),
        risk=RiskConfig(**raw.get("risk", {})),
        strategy=StrategyConfig(**raw.get("strategy", {})),
        execution=ExecutionConfig(**raw.get("execution", {})),
        screener=ScreenerConfig(**raw.get("screener", {})),
        state_file=raw.get("state_file", "state/portfolio.json"),
    )
    if cfg.execution.mode != "paper":
        raise ValueError(
            "execution.mode は現在 'paper' のみサポートしています。"
            "実運用には証券会社APIアダプタの実装と明示的な有効化が必要です。"
        )
    return cfg
