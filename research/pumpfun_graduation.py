"""Buy pump.fun coins the moment they graduate to PumpSwap and hold 1h / 6h / 24h.
Sample: graduated coins created 24-48h ago (pump.fun's API only lists the last ~2 days of graduations)."""
import requests, numpy as np, pandas as pd
from gecko import ohlcv
B = "https://frontend-api-v3.pump.fun/coins"
COST = 0.0125 + 0.01  # per side: ~1.25% swap/creator fees + ~1% tx/priority fees on a 0.1 SOL trade (approximate)

def graduated():
    rows = []
    for off in range(0, 1050, 50):
        g = requests.get(B, params=dict(offset=off, limit=50, sort="created_timestamp", order="DESC", complete="true", includeNsfw="true"), timeout=30).json()
        rows += [dict(mint=x["mint"], sym=x.get("symbol"), created=x["created_timestamp"], pool=x.get("pump_swap_pool") or x.get("pool_address")) for x in g]
    return pd.DataFrame(rows)

if __name__ == "__main__":
    g = graduated(); now = pd.Timestamp.now("UTC").timestamp() * 1000
    g = g[(g.created < now - 26 * 3600e3) & g.pool.notna()]
    s = g.sample(min(80, len(g)), random_state=0)
    print(len(g), "graduated coins created 26h+ ago; sampling", len(s), flush=True)
    res, bad = [], 0
    for x in s.itertuples():
        L = ohlcv(x.pool, "minute", 15, 1000, token=x.mint)
        if L is None or len(L) < 2: continue
        if not 5e3 < L[0, 4] * 1e9 < 5e5: bad += 1; continue   # entry market cap must be near graduation (~$30k)
        t0, entry = L[0, 0], L[0, 4]        # close of the first 15-minute candle on PumpSwap
        r = {"sym": x.sym}
        for h in (1, 6, 24):
            k = np.searchsorted(L[:, 0], t0 + h * 3600, side="right") - 1
            r[f"{h}h"] = L[k, 4] / entry * (1 - COST) ** 2 - 1
        r["max_24h"] = L[(L[:, 0] <= t0 + 86400), 4].max() / entry - 1   # closes: highs contain bad prints
        res.append(r)
    d = pd.DataFrame(res); print("dropped for implausible entry price:", bad)
    print(f"\n{len(d)} coins with PumpSwap price data; net of ~{COST*100:.2f}% per side\n")
    for c in ("1h", "6h", "24h"):
        x = d[c]; print(f"hold {c:>3s}: avg {x.mean()*100:+6.1f}%  median {x.median()*100:+6.1f}%  won {(x>0).mean()*100:3.0f}%  "
                       f"lost >50%: {(x<-0.5).mean()*100:3.0f}%  best {x.max()*100:+.0f}%")
    print(f"best 15-min close within 24h (perfect exit, gross): median {d.max_24h.median()*100:+.0f}%, >=+100% in {(d.max_24h>=1).mean()*100:.0f}% of coins")
    d.to_csv("data/pump/graduation_results.csv", index=False)
