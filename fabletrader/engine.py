"""Turns target weights into orders. Shared by the backtest and the live/paper
runner so that what was tested is what trades."""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config


@dataclass
class Order:
    asset: str
    side: str       # "buy" | "sell"
    qty: float      # base-currency amount
    quote: float    # estimated quote value


def plan_orders(cash: float, qty: dict[str, float], prices: dict[str, float],
                targets: dict[str, float], cfg: Config, cost: float) -> list[Order]:
    """Sells first, then buys sized to the cash that will actually be there.

    `cost` is the per-side fraction (fee + slippage) reserved when sizing buys.
    """
    equity = cash + sum(qty[a] * prices[a] for a in qty)
    deltas = {a: targets.get(a, 0.0) * equity - qty[a] * prices[a] for a in qty}
    floor = max(cfg.rebalance_band * equity, cfg.min_order_quote)
    orders: list[Order] = []
    for a in sorted(qty, key=lambda a: deltas[a]):
        d, px, held = deltas[a], prices[a], qty[a] * prices[a]
        if targets.get(a, 0.0) == 0.0:
            if held >= cfg.min_order_quote:  # full exit ignores the band
                orders.append(Order(a, "sell", qty[a], held))
                cash += held * (1 - cost)
            continue
        if abs(d) < floor:
            continue
        if d < 0:
            q = min(qty[a], -d / px)
            orders.append(Order(a, "sell", q, q * px))
            cash += q * px * (1 - cost)
        else:
            spend = min(d, cash / (1 + cost))
            if spend < cfg.min_order_quote:
                continue
            orders.append(Order(a, "buy", spend / px, spend))
            cash -= spend * (1 + cost)
    return orders
