"""Mirror image of the pump chase: SHORT a coin right after a pump (needs perpetual futures).
Entry next open, cover after 24h or at a stop-loss (filled at the stop, or worse if price gaps over it).
Ignores funding payments and assumes every coin had a perp, both of which flatter the result."""
import numpy as np, pandas as pd
from fast_trading import load, pump_events, MEME, DEFI
COST = 0.001  # per side: perp taker ~0.05% + slippage
data = load()
groups = {"memes": [s for s in data if s in MEME], "defi": [s for s in data if s in DEFI],
          "new listings": [s for s in data if s not in MEME and s not in DEFI]}
for g, syms in groups.items():
    for stop in (None, 0.30, 0.15):
        res = []
        for s in syms:
            d = data[s]; o, h = d.o.values, d.h.values
            for i in pump_events(d, 0.10, 5):
                if i + 26 >= len(d): continue
                e = o[i + 1]; x = o[i + 25]; worst = h[i + 1:i + 25].max() / e - 1
                if stop:
                    for j in range(i + 1, i + 25):
                        if o[j] >= e * (1 + stop): x = o[j]; break
                        if h[j] >= e * (1 + stop): x = e * (1 + stop); break
                res.append((pd.Timestamp(d.ts[i], unit="ms").year, (e - x) / e - 2 * COST, worst))
        r = pd.DataFrame(res, columns=["y", "ret", "worst_rise"])
        by = r.groupby("y").ret.mean().mul(100).round(1).to_dict()
        print(f"{g:13s} stop {str(stop):5s} n={len(r):5d} avg {r.ret.mean()*100:+5.2f}%  median {r.ret.median()*100:+5.2f}%  "
              f"won {(r.ret>0).mean()*100:3.0f}%  worst trade {r.ret.min()*100:5.0f}%  "
              f"trades where price rose 50%+ against you: {(r.worst_rise>0.5).sum()}  by year {by}")
