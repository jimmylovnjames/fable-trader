"""Are Polymarket prices biased in a way a bot can exploit?
For each resolved binary market, take the YES-token price H hours before the scheduled end (only if the
market was still open then), and check how often each side actually won versus the price paid.
Run fetch_polymarket.py first."""
import os, numpy as np, pandas as pd
from pathlib import Path
D = Path(__file__).resolve().parent / "data" / "poly"
SPREAD = 0.005   # half-spread paid to buy at the ask (history prices are ~mid); 0.5c is optimistic for thin markets

m = pd.read_csv(D / "markets.csv")
m["kind"] = np.where(m.slug.str.contains("updown|up-or-down", na=False), "crypto up/down", "everything else")
rows = []
for r in m.itertuples():
    f = D / "h" / f"{r.id}.csv"
    if not f.exists() or os.path.getsize(f) < 10: continue
    h = pd.read_csv(f)
    if h.empty: continue
    t, p = h.t.values, h.p.values
    end = pd.Timestamp(r.end).timestamp()
    closed = pd.Timestamp(r.closed).timestamp() if isinstance(r.closed, str) else end
    for H in (1, 6, 24, 72, 168):
        ts = end - H * 3600
        if closed <= ts: continue                      # already resolved: a live bot would not see it open
        k = np.searchsorted(t, ts, side="right") - 1
        if k < 0 or ts - t[k] > 2 * 3600: continue     # no price within 2h before the entry time
        p0 = float(p[k])
        if not 0.005 < p0 < 0.995: continue           # nothing to buy at 0 or 1
        fav_yes = p0 >= 0.5
        price = p0 if fav_yes else 1 - p0
        won = r.won0 if fav_yes else 1 - r.won0
        rows.append(dict(H=H, price=price, won=won, kind=r.kind, fees=bool(r.fees), vol=r.vol,
                         year=pd.Timestamp(r.end).year, half=f"{pd.Timestamp(r.end).year}H{1 + (pd.Timestamp(r.end).month > 6)}"))
df = pd.DataFrame(rows)
print(f"{df.groupby('H').size().to_dict()} market-entries (by hours before end) from {m.shape[0]} sampled markets\n")
bins = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 1.0]
df["bucket"] = pd.cut(df.price, bins, right=False)

def table(d, title):
    print(title)
    g = d.groupby("bucket", observed=True).agg(n=("won", "size"), avg_price=("price", "mean"), won=("won", "mean"))
    # buying the favourite at price+spread pays 1 if it wins
    g["edge_per_$"] = d.groupby("bucket", observed=True).apply(lambda x: (x.won / np.minimum(x.price + SPREAD, 0.999) - 1).mean(), include_groups=False)
    # buying the longshot (other side) at 1-price+spread
    g["longshot_edge_per_$"] = d.groupby("bucket", observed=True).apply(lambda x: ((1 - x.won) / (1 - x.price + SPREAD) - 1).mean(), include_groups=False)
    g["se"] = d.groupby("bucket", observed=True).apply(lambda x: (x.won / np.minimum(x.price + SPREAD, 0.999)).std() / np.sqrt(len(x)), include_groups=False)
    print((g.assign(avg_price=g.avg_price.round(3), won=g.won.round(3), **{"edge_per_$": (g["edge_per_$"] * 100).round(2),
          "longshot_edge_per_$": (g["longshot_edge_per_$"] * 100).round(1), "se": (g.se * 100).round(2)})).to_string(), "\n")

for H in (24, 1):
    table(df[df.H == H], f"=== favourite bought {H}h before scheduled end, all markets (edge and se in % per $ staked) ===")
for kind in ("crypto up/down", "everything else"):
    table(df[(df.H == 1) & (df.kind == kind)], f"=== 1h before end: {kind} ===")
print("=== 'buy every favourite >= 90c, 24h before end' by half-year: n / avg return per trade % ===")
x = df[(df.H == 24) & (df.price >= 0.9)]
print(x.groupby("half").apply(lambda g: pd.Series(dict(n=len(g), ret=(g.won / np.minimum(g.price + SPREAD, 0.999) - 1).mean() * 100,
      worst_streak_losses=(1 - g.won).sum())), include_groups=False).round(2).to_string())

# --- Underdog side (<= 10c): the only apparent edge. Re-priced at a realistic ask of 1.25x the mid
# (median ask/mid for underdogs in <$250k markets on live order books, measured 2026-11-24).
cat = np.select([m.q.str.contains("temperature", case=False),
                 m.q.str.contains("price of|bitcoin|ethereum|solana|xrp|up or down", case=False),
                 m.q.str.contains(" vs| o/u|exact score|win on|spread|halftime|score first", case=False)],
                ["weather", "crypto price", "sports"], "politics/other")
und = []
for r, c in zip(m.itertuples(), cat):
    f = D / "h" / f"{r.id}.csv"
    if not f.exists() or os.path.getsize(f) < 10: continue
    h = pd.read_csv(f); end = pd.Timestamp(r.end).timestamp()
    closed = pd.Timestamp(r.closed).timestamp() if isinstance(r.closed, str) else end
    for H in (24, 6):
        ts = end - H * 3600
        if closed <= ts: continue
        k = np.searchsorted(h.t.values, ts, side="right") - 1
        if k < 0 or ts - h.t.values[k] > 7200: continue
        p = h.p.values[k]; u = min(p, 1 - p)
        if not 0.005 < u <= 0.10: continue
        won = r.won0 if p < 0.5 else 1 - r.won0
        und.append(dict(H=H, cat=c, u=u, won=won, vol=r.vol, ret=won / (1.25 * u) - 1,
                        half=f"{pd.Timestamp(r.end).year}H{1 + (pd.Timestamp(r.end).month > 6)}"))
u = pd.DataFrame(und)
u["vtier"] = pd.cut(u.vol, [0, 5e4, 2.5e5, 1e6, np.inf], labels=["10-50k", "50-250k", "250k-1M", ">1M"])
for H in (24, 6):
    x = u[u.H == H]
    print(f"\n=== underdogs <= 10c bought {H}h before end at 1.25x mid: return per $ ===")
    print(x.groupby("vtier", observed=True).agg(n=("ret", "size"), won=("won", "mean"), ret=("ret", "mean")).round(3).to_string())
    y = x[x.vol < 2.5e5]
    print(y.groupby("cat").agg(n=("ret", "size"), price=("u", "mean"), won=("won", "mean"), ret=("ret", "mean")).round(3).to_string())
    print("thin markets by half-year:", y.groupby("half").ret.mean().round(2).to_dict())
