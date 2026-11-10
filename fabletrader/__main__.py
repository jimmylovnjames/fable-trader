from __future__ import annotations

import argparse
import logging

import pandas as pd

from . import bot
from .backtest import run_backtest, stats
from .config import load_config, load_dotenv
from .data import fetch_history


def cmd_backtest(cfg, args) -> None:
    hist = {a: fetch_history(a, args.start) for a in cfg.assets}
    opens = pd.DataFrame({a: h.open for a, h in hist.items()}).dropna()
    closes = pd.DataFrame({a: h.close for a, h in hist.items()}).dropna()
    cfg.max_drawdown = 1.0  # report the raw strategy, kill switch off
    bt = run_backtest(opens, closes, cfg, cash=args.cash)
    eq = bt.equity.iloc[cfg.warmup:]
    hold = (closes.loc[eq.index] / closes.loc[eq.index].iloc[0]).mean(axis=1) * eq.iloc[0]
    print(f"{'+'.join(cfg.assets)} vs USDT, {eq.index[0].date()} -> {eq.index[-1].date()}, "
          f"start {args.cash:.0f}, cost/side {(cfg.paper_fee + cfg.paper_slippage) * 100:.2f}%")
    print(f"{'':14s}{'final':>10s}{'CAGR':>8s}{'vol':>8s}{'Sharpe':>8s}{'max DD':>8s}")
    for name, s in (("strategy", eq), ("buy & hold", hold)):
        m = stats(s)
        print(f"{name:14s}{s.iloc[-1]:10.0f}{m['cagr'] * 100:7.1f}%{m['vol'] * 100:7.1f}%"
              f"{m['sharpe']:8.2f}{m['max_drawdown'] * 100:7.1f}%")
    yearly = eq.groupby(eq.index.year).agg(lambda s: s.iloc[-1] / s.iloc[0] - 1)
    hy = hold.groupby(hold.index.year).agg(lambda s: s.iloc[-1] / s.iloc[0] - 1)
    print("\nyear   strategy   buy&hold")
    for y in yearly.index:
        print(f"{y}   {yearly[y] * 100:7.1f}%   {hy[y] * 100:7.1f}%")
    n = len(eq) / 365
    print(f"\ntrades/yr {bt.trades.loc[eq.index].sum() / n:.0f}, avg exposure {bt.exposure.loc[eq.index].mean() * 100:.0f}%")


def main() -> int:
    p = argparse.ArgumentParser(prog="fabletrader", description=__doc__)
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="trade (paper unless --live)")
    r.add_argument("--live", action="store_true", help="send REAL orders")
    r.add_argument("--once", action="store_true", help="single cycle then exit (cron / CI)")
    r.add_argument("--force", action="store_true", help="re-run even if today's bar was traded")
    s = sub.add_parser("status", help="show balances and state")
    s.add_argument("--live", action="store_true")
    b = sub.add_parser("backtest", help="replay the strategy on full history")
    b.add_argument("--start", default="2017-01-01")
    b.add_argument("--cash", type=float, default=100.0)
    sub.add_parser("reset", help="clear the kill-switch halt and drawdown peak")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    cfg = load_config(args.config)
    if args.cmd == "backtest":
        cmd_backtest(cfg, args)
    elif args.cmd == "status":
        bot.status(cfg, args.live)
    elif args.cmd == "reset":
        st = bot.load_state(cfg)
        st.pop("halted", None)
        st.pop("peak_equity", None)
        bot.save_state(cfg, st)
        print("halt cleared")
    else:
        return bot.run(cfg, args.live, args.once, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
