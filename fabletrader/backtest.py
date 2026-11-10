"""Event-driven backtest: signal on close[t], fill at open[t+1],
fee + slippage on every fill, same rebalance band and minimum order as live."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .engine import plan_orders
from .strategy import target_weights


def run_backtest(opens: pd.DataFrame, closes: pd.DataFrame, cfg: Config,
                 cash: float = 100.0, fee: float | None = None,
                 slippage: float | None = None) -> pd.DataFrame:
    fee = cfg.paper_fee if fee is None else fee
    slippage = cfg.paper_slippage if slippage is None else slippage
    cost = fee + slippage
    w = target_weights(closes, cfg)
    assets = list(closes.columns)
    qty = dict.fromkeys(assets, 0.0)
    peak, halted, rows = cash, False, []
    for i in range(1, len(closes)):
        px = opens.iloc[i]
        equity = cash + sum(qty[a] * px[a] for a in assets)
        peak = max(peak, equity)
        if not halted and equity < peak * (1 - cfg.max_drawdown):
            halted = True
        tgt = {a: 0.0 if halted else w.iloc[i - 1][a] for a in assets}
        orders = plan_orders(cash, qty, px.to_dict(), tgt, cfg, cost)
        for o in orders:
            if o.side == "sell":
                cash += o.quote * (1 - cost)
                qty[o.asset] -= o.qty
            else:
                cash -= o.quote * (1 + cost)
                qty[o.asset] += o.qty
        trades = len(orders)
        c = closes.iloc[i]
        rows.append({"date": closes.index[i], "trades": trades, "halted": halted,
                     "equity": cash + sum(qty[a] * c[a] for a in assets),
                     "exposure": sum(qty[a] * c[a] for a in assets) / (cash + sum(qty[a] * c[a] for a in assets))})
    return pd.DataFrame(rows).set_index("date")


def stats(equity: pd.Series) -> dict[str, float]:
    r = equity.pct_change().dropna()
    years = len(equity) / 365
    dd = equity / equity.cummax() - 1
    return {
        "total_return": equity.iloc[-1] / equity.iloc[0] - 1,
        "cagr": (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1,
        "vol": r.std() * np.sqrt(365),
        "sharpe": r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0,
        "max_drawdown": dd.min(),
    }
