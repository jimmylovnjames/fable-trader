"""Brokers: PaperBroker simulates fills against live prices; LiveBroker sends
real market orders through ccxt. Same interface, so the runner cannot tell."""
from __future__ import annotations

import logging

from .config import Config
from .engine import Order

log = logging.getLogger("fabletrader")


class PaperBroker:
    live = False

    def __init__(self, ex, cfg: Config, state: dict):
        self.ex, self.cfg = ex, cfg
        self.book = state.setdefault("paper", {"cash": cfg.paper_start_cash, "qty": {}})
        self.cost = cfg.paper_fee + cfg.paper_slippage

    def prices(self) -> dict[str, float]:
        return {a: float(self.ex.fetch_ticker(self.cfg.symbol(a))["last"]) for a in self.cfg.assets}

    def balances(self) -> tuple[float, dict[str, float]]:
        return self.book["cash"], {a: self.book["qty"].get(a, 0.0) for a in self.cfg.assets}

    def execute(self, o: Order, price: float) -> None:
        q = self.book["qty"]
        if o.side == "sell":
            sold = min(o.qty, q.get(o.asset, 0.0))
            self.book["cash"] += sold * price * (1 - self.cost)
            q[o.asset] = q.get(o.asset, 0.0) - sold
        else:
            spend = min(o.qty * price, self.book["cash"] / (1 + self.cost))
            self.book["cash"] -= spend * (1 + self.cost)
            q[o.asset] = q.get(o.asset, 0.0) + spend / price


class LiveBroker:
    live = True
    cost = 0.01  # cash reserved per buy for fee + market-order slippage

    def __init__(self, ex, cfg: Config):
        self.ex, self.cfg = ex, cfg
        self.ex.load_markets()
        missing = [s for s in cfg.symbols if s not in self.ex.markets]
        if missing:
            raise SystemExit(f"{ex.id} does not list {missing}; change `quote`/`assets` in config.yaml")

    def prices(self) -> dict[str, float]:
        return {a: float(self.ex.fetch_ticker(self.cfg.symbol(a))["last"]) for a in self.cfg.assets}

    def balances(self) -> tuple[float, dict[str, float]]:
        total = self.ex.fetch_balance()["total"]
        return float(total.get(self.cfg.quote) or 0.0), {a: float(total.get(a) or 0.0) for a in self.cfg.assets}

    def execute(self, o: Order, price: float) -> None:
        symbol = self.cfg.symbol(o.asset)
        limits = self.ex.market(symbol).get("limits", {})
        qty = float(self.ex.amount_to_precision(symbol, o.qty))
        min_amt = (limits.get("amount") or {}).get("min") or 0.0
        min_cost = (limits.get("cost") or {}).get("min") or 0.0
        if qty <= 0 or qty < min_amt or qty * price < min_cost:
            log.warning("skip %s %s %.8f: below %s minimum order size", o.side, symbol, qty, self.ex.id)
            return
        res = self.ex.create_order(symbol, "market", o.side, qty)
        log.info("order %s: %s %s %.8f", res.get("id"), o.side, symbol, qty)
