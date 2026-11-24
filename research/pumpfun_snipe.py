"""Snipe brand-new pump.fun coins: buy in the first minute, sell at +100% / -50% / 30 minutes.
Population: every SOL-quoted coin collect_pumpfun.py saw until 40+ minutes old.
Prices: GeckoTerminal 1-minute candles on the bonding curve, for a sample stratified by how high each
coin ever went, re-weighted to the full population. Stops use candle closes (some lows are bad prints)."""
import sys, numpy as np, pandas as pd
from gecko import ohlcv
FEE, FIXED = 0.0125, 0.015   # ~1.25% per side pump.fun fees; ~0.0015 SOL priority/tip per round trip on 0.1 SOL
c = pd.read_csv("data/pump/coins.csv")
c["age_min"] = (c.seen_at - c.created_timestamp) / 60000
sol = (c.usd_market_cap / c.market_cap).median(); start_mc = 27.96 * sol   # curve starts at ~27.96 SOL market cap
# SOL-quoted coins only (coins quoted in other tokens report a market cap of 0), observed until 40+ min old
pop = c[(c.age_min >= 40) & (c.market_cap > 0) & (c.usd_market_cap > 0)].copy()
pop["ath_x"] = pop.ath_market_cap / start_mc; pop["now_x"] = pop.usd_market_cap / start_mc
print(f"{len(pop)} SOL-quoted coins observed until {pop.age_min.median():.0f} min old (SOL ${sol:.0f}); "
      f"standard curve start = ${start_mc:,.0f} market cap")
print(f"graduated: {pop.complete.mean()*100:.2f}%   peak market cap >= $5k: {(pop.ath_market_cap>=5e3).mean()*100:.1f}%   "
      f">= $20k: {(pop.ath_market_cap>=2e4).mean()*100:.1f}%   >= $50k: {(pop.ath_market_cap>=5e4).mean()*100:.1f}%")
print(f"market cap at ~40 min: median ${pop.usd_market_cap.median():,.0f}; at or below the curve start: {(pop.now_x<=1.01).mean()*100:.0f}%\n")

bins = [0, 3e3, 6e3, 2e4, np.inf]; pop["stratum"] = pd.cut(pop.ath_market_cap, bins, right=False,
                                                          labels=["peak <$3k", "peak $3-6k", "peak $6-20k", "peak >=$20k"])
per = int(sys.argv[1]) if len(sys.argv) > 1 else 60
sample = pd.concat([g.sample(min(per, len(g)), random_state=0) for _, g in pop.groupby("stratum", observed=True)])

def sim(L, entry_kind):
    if L is None: return None
    if len(L) == 0: return -2 * FEE - FIXED        # nobody else ever traded: in and out at the same price
    o0, c0 = L[0, 1], L[0, 4]
    entry = (o0 if o0 >= 0.5 * c0 else c0) if entry_kind == "seconds" else c0   # opens below half the close are bad prints
    t_in = L[0, 0]
    for t, o, h, l, cl, v in L[1:] if entry_kind == "minute" else L:
        if t > t_in + 30 * 60: break
        if h >= 2 * entry: return 2 * (1 - FEE) ** 2 - 1 - FIXED   # take profit at +100% (optimistic fill)
        if cl <= 0.5 * entry: return (cl / entry) * (1 - FEE) ** 2 - 1 - FIXED
    k = np.searchsorted(L[:, 0], t_in + 30 * 60, side="right") - 1
    return L[max(k, 0), 4] / entry * (1 - FEE) ** 2 - 1 - FIXED

if __name__ == "__main__":
    rows = []
    for x in sample.itertuples():
        L = ohlcv(x.bonding_curve, "minute", 1, 1000, token=x.mint)
        rows.append(dict(stratum=x.stratum, minute=sim(L, "minute"), seconds=sim(L, "seconds"),
                         first_close_mc=L[0, 4] * 1e9 if L is not None and len(L) else np.nan))
    r = pd.DataFrame(rows).dropna(subset=["minute"])
    w = pop.stratum.value_counts(normalize=True)
    print("stratum (peak market cap)                 pop share   n sampled   avg net: buy in first seconds | buy at end of minute 1")
    for s, g in r.groupby("stratum", observed=True):
        print(f"  {str(s):28s}          {w[s]*100:6.1f}%   {len(g):5d}       {g.seconds.mean()*100:+7.1f}%            {g.minute.mean()*100:+7.1f}%")
    for col, name in (("seconds", "buy in the first seconds (optimistic)"), ("minute", "buy at end of first minute")):
        m = sum(w[s] * g[col].mean() for s, g in r.groupby("stratum", observed=True))
        won = sum(w[s] * (g[col] > 0).mean() for s, g in r.groupby("stratum", observed=True))
        print(f"\nPOPULATION-WEIGHTED, {name}: avg {m*100:+.1f}% per trade, wins {won*100:.0f}% of trades")
    print(f"\nmedian market cap at the end of minute 1: ${r.first_close_mc.median():,.0f} (curve start ${start_mc:,.0f})")
    r.to_csv("data/pump/snipe_results.csv", index=False)
