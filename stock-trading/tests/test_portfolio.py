import pytest

from autotrader.portfolio.portfolio import Portfolio


def test_buy_and_sell_flow():
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2024-01-05", "7203.T", 100, 2500, 125, "test buy")
    assert p.cash == 1_000_000 - 250_000 - 125
    assert p.positions["7203.T"].quantity == 100

    p.apply_sell("2024-02-01", "7203.T", 100, 2700, 135, "test sell")
    assert "7203.T" not in p.positions
    assert p.cash == 1_000_000 - 250_125 + 270_000 - 135
    assert len(p.trades) == 2


def test_buy_averages_cost():
    p = Portfolio(cash=10_000_000)
    p.apply_buy("2024-01-05", "X", 100, 1000, 0, "")
    p.apply_buy("2024-01-06", "X", 100, 2000, 0, "")
    assert p.positions["X"].avg_cost == 1500
    assert p.positions["X"].quantity == 200


def test_insufficient_cash_rejected():
    p = Portfolio(cash=1000)
    with pytest.raises(ValueError):
        p.apply_buy("2024-01-05", "X", 100, 1000, 0, "")


def test_oversell_rejected():
    p = Portfolio(cash=1_000_000)
    p.apply_buy("2024-01-05", "X", 100, 1000, 0, "")
    with pytest.raises(ValueError):
        p.apply_sell("2024-01-06", "X", 200, 1000, 0, "")


def test_save_and_load(tmp_path):
    path = str(tmp_path / "state.json")
    p = Portfolio(cash=500_000)
    p.apply_buy("2024-01-05", "X", 100, 1000, 50, "persist test")
    p.save(path)

    loaded = Portfolio.load(path, initial_capital=999)
    assert loaded.cash == p.cash
    assert loaded.positions["X"].quantity == 100
    assert loaded.trades[0].reason == "persist test"


def test_load_missing_creates_fresh(tmp_path):
    loaded = Portfolio.load(str(tmp_path / "none.json"), initial_capital=123)
    assert loaded.cash == 123
    assert not loaded.positions
