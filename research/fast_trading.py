"""Fast trading on volatile coins (memes, DeFi, every Binance listing since 2024), hourly bars.
Pump chase: buy after a big up-hour on a volume spike. Breakout: buy a new 48h high, sell a new 24h low.
Signals on the bar close, fills at the next bar's open. Run research/fetch_hourly.py first."""
import os, numpy as np, pandas as pd
from pathlib import Path
H = Path(__file__).resolve().parent / "data" / "hourly_all"
from fetch_hourly import MEME, DEFI

def load():
    out = {}
    for f in sorted(os.listdir(H)):
        d = pd.read_csv(H / f)
        if len(d) > 500: out[f[:-4]] = d
    return out

def pump_events(d, jump, vmult):
    r = d.c / d.o - 1
    vspike = d.qv > vmult * d.qv.rolling(72, min_periods=48).median().shift(1)
    return np.flatnonzero((r > jump) & vspike)

def exit_fixed(d, i, h):
    j = min(i + 1 + h, len(d) - 1)
    return d.o.values[j] / d.o.values[i + 1] - 1, j

def exit_trail(d, i, trail, maxh):
    o, c = d.o.values, d.c.values
    e = o[i + 1]; peak = e; j = i + 1
    while j < len(d) - 1 and j - i <= maxh:
        peak = max(peak, c[j])
        if c[j] < peak * (1 - trail): break
        j += 1
    j = min(j + 1, len(d) - 1)
    return o[j] / e - 1, j

def breakout_trades(d, nin=48, nout=24):
    o, c = d.o.values, d.c.values
    hi = d.h.rolling(nin).max().shift(1).values; lo = d.l.rolling(nout).min().shift(1).values
    out, i, n = [], nin + 1, len(d)
    while i < n - 2:
        if c[i] > hi[i]:
            e, j = o[i + 1], i + 1
            while j < n - 2 and not (c[j] < lo[j]): j += 1
            out.append((i, o[j + 1] / e - 1, j - i)); i = j + 1
        else: i += 1
    return out

def summarize(name, trades, ts):
    """trades: list of (symbol, signal_index, gross_return, bars_held); ts: symbol -> timestamps"""
    if not trades: print(f"{name:42s} no trades"); return
    r = np.array([t[2] for t in trades]); yrs = np.array([pd.Timestamp(ts[t[0]][t[1]], unit="ms").year for t in trades])
    line = f"{name:42s} n={len(r):6d} won {np.mean(r>0)*100:3.0f}% gross {r.mean()*100:+6.2f}% hold {np.mean([t[3] for t in trades]):4.0f}h |"
    for cost in (0.001, 0.004, 0.006):
        net = (1 + r) * (1 - cost) ** 2 - 1
        line += f" @{cost*100:.1f}%: {net.mean()*100:+6.2f}%"
    early, late = r[yrs <= 2024], r[yrs >= 2025]
    line += f" | net@0.4% 23-24 {((1+early)*.996**2-1).mean()*100:+.2f}%  25-26 {((1+late)*.996**2-1).mean()*100:+.2f}%"
    print(line)

if __name__ == "__main__":
    data = load(); ts = {s: d.ts.values for s, d in data.items()}
    groups = {"memes": [s for s in data if s in MEME], "defi": [s for s in data if s in DEFI],
              "new listings": [s for s in data if s not in MEME and s not in DEFI]}
    print({g: len(v) for g, v in groups.items()}, "\n")
    print("avg per trade, net of cost per side; columns: 0.1% (Binance-level), 0.4% (Kraken), 0.6% (Kraken + meme slippage)\n")
    for g, syms in groups.items():
        print(f"--- {g} ---")
        for jump, vm in ((0.05, 5), (0.10, 5)):
            ev = [(s, i) for s in syms for i in pump_events(data[s], jump, vm) if i < len(data[s]) - 2]
            for h in (1, 4, 24):
                summarize(f"pump >{jump*100:.0f}%/1h, vol x{vm}, hold {h}h", [(s, i, *exit_fixed(data[s], i, h)[:1], h) for s, i in ev], ts)
            tr = []
            for s, i in ev:
                r, j = exit_trail(data[s], i, 0.05, 48); tr.append((s, i, r, j - i))
            summarize(f"pump >{jump*100:.0f}%/1h, vol x{vm}, 5% trailing stop", tr, ts)
        tr = [(s, i, r, h) for s in syms for i, r, h in breakout_trades(data[s])]
        summarize("breakout: 48h high in, 24h low out", tr, ts)
        tr = [(s, i, r, h) for s in syms for i, r, h in breakout_trades(data[s], 24, 12)]
        summarize("breakout: 24h high in, 12h low out", tr, ts)
        print()
