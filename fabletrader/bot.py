"""The runner: one `tick` per completed daily candle."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

from .broker import LiveBroker, PaperBroker
from .config import Config
from .data import live_closes, make_exchange
from .engine import plan_orders
from .strategy import latest_weights

log = logging.getLogger("fabletrader")


def load_state(cfg: Config) -> dict:
    p = Path(cfg.state_file)
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(cfg: Config, state: dict) -> None:
    tmp = Path(cfg.state_file + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(cfg.state_file)


def make_broker(cfg: Config, state: dict, live: bool):
    mode = "live" if live else "paper"
    if state.setdefault("mode", mode) != mode:
        raise SystemExit(f"{cfg.state_file} belongs to a {state['mode']} run; "
                         f"delete it (or set a different state_file) to start {mode} trading")
    if live:
        return LiveBroker(make_exchange(cfg.exchange, auth=True), cfg)
    return PaperBroker(make_exchange(cfg.exchange), cfg, state)


def tick(cfg: Config, broker, state: dict, force: bool = False) -> bool:
    """Run one decision cycle. Returns False if any order failed."""
    closes = live_closes(broker.ex, cfg.symbols, cfg.warmup + 5)
    closes.columns = cfg.assets
    bar = str(closes.index[-1].date())
    prices = broker.prices()
    cash, qty = broker.balances()
    equity = cash + sum(qty[a] * prices[a] for a in cfg.assets)
    peak = state["peak_equity"] = max(state.get("peak_equity", 0.0), equity)
    drawdown = 1 - equity / peak if peak > 0 else 0.0
    if drawdown >= cfg.max_drawdown and not state.get("halted"):
        state["halted"] = True
        log.error("KILL SWITCH: drawdown %.1f%% >= %.0f%%. Flattening and halting. "
                  "Run `reset` to resume.", drawdown * 100, cfg.max_drawdown * 100)

    if state.get("halted"):
        targets = dict.fromkeys(cfg.assets, 0.0)
    elif state.get("last_bar") == bar and not force:
        log.info("bar %s already traded; equity %.2f %s", bar, equity, cfg.quote)
        return True
    else:
        targets = latest_weights(closes, cfg)

    log.info("bar %s | equity %.2f %s | drawdown %.1f%% | targets %s", bar, equity, cfg.quote,
             drawdown * 100, {a: round(w, 3) for a, w in targets.items()})
    ok = True
    for o in plan_orders(cash, qty, prices, targets, cfg, broker.cost):
        log.info("%s %s %.8f (~%.2f %s)", o.side.upper(), o.asset, o.qty, o.quote, cfg.quote)
        try:
            broker.execute(o, prices[o.asset])
        except Exception:
            ok = False
            log.exception("order failed: %s %s", o.side, o.asset)
    if ok:
        state["last_bar"] = bar
    state.setdefault("history", []).append({"bar": bar, "equity": round(equity, 2)})
    state["history"] = state["history"][-730:]
    return ok


def run(cfg: Config, live: bool, once: bool, force: bool = False) -> int:
    state = load_state(cfg)
    broker = make_broker(cfg, state, live)
    log.info("mode=%s exchange=%s pairs=%s", "LIVE" if live else "paper", cfg.exchange, cfg.symbols)
    while True:
        try:
            ok = tick(cfg, broker, state, force)
        except Exception:
            ok = False
            log.exception("tick failed")
        save_state(cfg, state)
        if once:
            return 0 if ok else 1
        now = pd.Timestamp.now("UTC")
        # daily candle closes at 00:00 UTC; on failure retry in 10 minutes
        wake = now.normalize() + pd.Timedelta(days=1, minutes=5) if ok else now + pd.Timedelta(minutes=10)
        log.info("sleeping until %s", wake.strftime("%Y-%m-%d %H:%M UTC"))
        time.sleep(max(60, (wake - now).total_seconds()))


def status(cfg: Config, live: bool) -> None:
    state = load_state(cfg)
    broker = make_broker(cfg, state, live)
    prices = broker.prices()
    cash, qty = broker.balances()
    equity = cash + sum(qty[a] * prices[a] for a in cfg.assets)
    print(f"mode     {'LIVE' if live else 'paper'} on {cfg.exchange}")
    print(f"equity   {equity:.2f} {cfg.quote}   (peak {max(state.get('peak_equity', 0), equity):.2f})")
    print(f"cash     {cash:.2f} {cfg.quote}")
    for a in cfg.assets:
        v = qty[a] * prices[a]
        print(f"{a:8s} {qty[a]:.8f} = {v:.2f} {cfg.quote} ({v / equity * 100 if equity else 0:.0f}%)")
    print(f"halted   {bool(state.get('halted'))}   last bar traded: {state.get('last_bar')}")
