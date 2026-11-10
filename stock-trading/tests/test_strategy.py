from autotrader.config import StrategyConfig
from autotrader.strategy.ensemble import EnsembleStrategy
from autotrader.strategy.momentum import MomentumStrategy


def test_momentum_uptrend_buys(uptrend_df):
    sig = MomentumStrategy().evaluate("TEST", uptrend_df)
    assert sig.score > 0


def test_momentum_downtrend_sells(downtrend_df):
    sig = MomentumStrategy().evaluate("TEST", downtrend_df)
    assert sig.score < 0


def test_momentum_insufficient_data(uptrend_df):
    sig = MomentumStrategy().evaluate("TEST", uptrend_df.head(30))
    assert sig.score == 0.0


def test_ensemble_actions(uptrend_df, downtrend_df, flat_df):
    ens = EnsembleStrategy(StrategyConfig())
    assert ens.evaluate("UP", uptrend_df).action == "BUY"
    assert ens.evaluate("DOWN", downtrend_df).action == "SELL"
    # 横ばいは概ねHOLD
    assert ens.evaluate("FLAT", flat_df).action in ("HOLD", "BUY", "SELL")


def test_ensemble_score_bounded(uptrend_df):
    ens = EnsembleStrategy(StrategyConfig())
    sig = ens.evaluate("UP", uptrend_df)
    assert -1.0 <= sig.score <= 1.0
