"""Buy every new Binance USDT listing and hold for N days. Daily data, delisted coins included.
Run research/altcoin_basket.py first (it downloads research/data/daily)."""
import os, re, numpy as np, pandas as pd
from pathlib import Path
D = Path(__file__).resolve().parent / "data" / "daily"
STABLE = {"USDC","BUSD","TUSD","USDP","PAX","DAI","UST","FDUSD","USDS","AEUR","EUR","GBP","AUD","EURI","USD1","PYUSD","BFUSD","XUSD","RLUSD","USDE","PAXG","WBTC","WBETH","BETH","XAUT","BNSOL","U"}
COST = 0.005  # per side: Kraken 0.4% taker + 0.1% slippage (optimistic on listing days)

rows = []
for f in os.listdir(D):
    b = f[:-8]
    d = pd.read_csv(D / f)
    if b in STABLE or re.match(r".+(UP|DOWN|BULL|BEAR)$", b) or len(d) < 3: continue
    t0 = pd.to_datetime(d.ts[0], unit="ms")
    if t0 < pd.Timestamp("2019-01-01"): continue
    if d.c.pct_change().std() < 0.01: continue  # stablecoins / pegged
    c, o = d.c.values, d.o.values
    r = {"sym": b, "listed": t0, "day1": c[0] / o[0] - 1}
    for h in (1, 7, 30, 90, 365):
        r[f"open->{h}d"] = c[min(h, len(c) - 1)] / o[0] - 1          # sniper: fill at first print
        r[f"close1->{h}d"] = c[min(h, len(c) - 1)] / c[0] - 1         # realistic: buy end of day 1
        r[f"green1->{h}d"] = r[f"close1->{h}d"] if c[0] > o[0] else np.nan  # only if day 1 closed up
    rows.append(r)
df = pd.DataFrame(rows)
print(f"{len(df)} listings since 2019\n")
print(f"{'entry -> exit':16s}{'n':>5s}{'avg net':>9s}{'median':>9s}{'% won':>7s}{'worst':>7s}{'best':>8s}")
for k in [c for c in df.columns if "->" in c]:
    x = df[k].dropna(); net = (1 + x) * (1 - COST) ** 2 - 1
    print(f"{k:16s}{len(x):5d}{net.mean()*100:8.1f}%{net.median()*100:8.1f}%{(net>0).mean()*100:6.0f}%{net.min()*100:6.0f}%{net.max()*100:7.0f}%")
print("\nbuy end of day 1, hold 30 days, by listing year (median / % won):")
df["net30"] = (1 + df["close1->30d"]) * (1 - COST) ** 2 - 1
print(df.groupby(df.listed.dt.year).net30.agg(n="count", median="median", won=lambda s: (s > 0).mean()).round(3).to_string())
