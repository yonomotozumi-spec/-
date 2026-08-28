import pytest

from autotrader.execution.kabu import KabuBroker


@pytest.fixture
def broker(monkeypatch):
    monkeypatch.setenv("KABU_API_PASSWORD", "api-pass")
    monkeypatch.setenv("KABU_ORDER_PASSWORD", "order-pass")
    monkeypatch.setenv("KABU_CONFIRM_LIVE", "yes")
    b = KabuBroker()
    b_calls = []

    def fake_request(method, path, body=None, token=None):
        b_calls.append((method, path, body, token))
        if path == "/token":
            return {"Token": "tok123"}
        if path == "/sendorder":
            return {"Result": 0, "OrderId": "ORD1"}
        if path.startswith("/orders"):
            return [{"ID": "ORD1", "State": 5,
                     "Details": [{"RecType": 8, "Price": 1751.0, "Qty": 100}]}]
        return {}

    b._request = fake_request
    b.calls = b_calls
    return b


def test_safety_guard_without_confirm(monkeypatch):
    monkeypatch.setenv("KABU_API_PASSWORD", "x")
    monkeypatch.setenv("KABU_ORDER_PASSWORD", "y")
    monkeypatch.delenv("KABU_CONFIRM_LIVE", raising=False)
    with pytest.raises(RuntimeError, match="KABU_CONFIRM_LIVE"):
        KabuBroker()


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("KABU_API_PASSWORD", raising=False)
    monkeypatch.delenv("KABU_ORDER_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="環境変数"):
        KabuBroker()


def test_buy_order_flow(broker):
    fill = broker.execute("8309.T", "BUY", 100, ref_price=1750.0)
    assert fill.price == 1751.0  # 約定照会から取得
    assert fill.quantity == 100
    send = [c for c in broker.calls if c[1] == "/sendorder"][0]
    body = send[2]
    assert body["Symbol"] == "8309"      # .T が除去される
    assert body["Exchange"] == 9         # SOR
    assert body["Side"] == "2"           # 買い
    assert body["FrontOrderType"] == 10  # 成行
    assert send[3] == "tok123"           # トークン付与


def test_rejects_non_board_lot(broker):
    with pytest.raises(ValueError, match="単元"):
        broker.execute("8309.T", "BUY", 150, ref_price=1750.0)


def test_daily_order_limit(broker):
    broker.max_orders_per_day = 1
    broker.execute("8309.T", "BUY", 100, ref_price=1750.0)
    with pytest.raises(ValueError, match="上限"):
        broker.execute("2801.T", "BUY", 100, ref_price=1800.0)


def test_send_error_raises(broker):
    orig = broker._request

    def failing(method, path, body=None, token=None):
        if path == "/sendorder":
            return {"Result": 4, "OrderId": ""}
        return orig(method, path, body, token)

    broker._request = failing
    with pytest.raises(ValueError, match="発注エラー"):
        broker.execute("8309.T", "BUY", 100, ref_price=1750.0)
