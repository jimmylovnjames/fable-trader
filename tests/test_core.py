import numpy as np
import pandas as pd
import pytest

from fabletrader.backtest import run_backtest
from fabletrader.bot import tick
from fabletrader.broker import PaperBroker
from fabletrader.config import Config
from fabletrader.engine import plan_orders
from fabletrader.strategy import target_weights


def prices(n=400, seed=0, drift=0.001):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({a: 100 * np.exp(np.cumsum(rng.normal(drift, 0.03, n))) for a in ("BTC", "ETH")}, index=idx)


def test_weights_bounded_and_flat_during_warmup():
    cfg = Config()
    w = target_weights(prices(), cfg)
    assert (w >= 0).all().all()
    assert (w.sum(axis=1) <= cfg.max_exposure + 1e-12).all()
    assert (w.iloc[: max(cfg.trend_windows) - 1] == 0).all().all()


def test_no_lookahead():
    cfg, p = Config(), prices()
    full = target_weights(p, cfg)
    mutated = p.copy()
    mutated.iloc[300:] *= 5
    pd.testing.assert_frame_equal(full.iloc[:300], target_weights(mutated, cfg).iloc[:300])


def test_downtrend_goes_to_cash():
    w = target_weights(prices(drift=-0.01), Config())
    assert w.iloc[-1].sum() < 0.05


def test_plan_respects_band_min_order_and_cash():
    cfg = Config()
    px = {"BTC": 100.0, "ETH": 100.0}
    # inside the band -> nothing
    assert plan_orders(50, {"BTC": 0.5, "ETH": 0.0}, px, {"BTC": 0.55, "ETH": 0.0}, cfg, 0.005) == []
    # full exit ignores the band, sell comes before the buy it funds
    o = plan_orders(0, {"BTC": 1.0, "ETH": 0.0}, px, {"BTC": 0.0, "ETH": 0.5}, cfg, 0.005)
    assert [(x.asset, x.side) for x in o] == [("BTC", "sell"), ("ETH", "buy")]
    assert o[0].qty == 1.0
    # buys never exceed available cash after costs
    o = plan_orders(20, {"BTC": 0.0, "ETH": 0.0}, px, {"BTC": 1.0, "ETH": 0.0}, cfg, 0.01)
    assert o[0].quote * 1.01 <= 20 + 1e-9
    # dust below the minimum order is left alone
    assert plan_orders(100, {"BTC": 0.01, "ETH": 0.0}, px, {"BTC": 0.0, "ETH": 0.0}, cfg, 0.005) == []


def test_backtest_costs_reduce_equity_and_cash_never_negative():
    p = prices()
    free = run_backtest(p, p, Config(max_drawdown=1.0), fee=0, slippage=0)
    paid = run_backtest(p, p, Config(max_drawdown=1.0))
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
    assert paid.trades.sum() > 0
    assert (paid.exposure <= 1 + 1e-9).all()


class FakeExchange:
    id = "fake"

    def __init__(self, closes):
        self.closes = closes

    def fetch_ohlcv(self, symbol, tf, limit):
        s = self.closes[symbol.split("/")[0]]
        return [[int(t.timestamp() * 1000), v, v, v, v, 0] for t, v in s.items()][-limit:]

    def fetch_ticker(self, symbol):
        return {"last": float(self.closes[symbol.split("/")[0]].iloc[-1])}


def test_paper_tick_is_idempotent_and_kill_switch_flattens(tmp_path):
    cfg = Config(state_file=str(tmp_path / "s.json"))
    p = prices(drift=0.004)
    ex, state = FakeExchange(p), {}
    broker = PaperBroker(ex, cfg, state)
    assert tick(cfg, broker, state)
    cash1, qty1 = broker.balances()
    assert cash1 < cfg.paper_start_cash and sum(qty1.values()) > 0
    assert tick(cfg, broker, state)  # same bar: no further trades
    assert broker.balances() == (cash1, qty1)

    ex.closes = p * 0.2  # crash -> drawdown beyond the limit
    assert tick(cfg, broker, state)
    assert state["halted"]
    cash, qty = broker.balances()
    assert sum(q * 20 for q in qty.values()) < cfg.min_order_quote * 2  # only dust left
    assert cash == pytest.approx(broker.book["cash"]) and cash > 0
