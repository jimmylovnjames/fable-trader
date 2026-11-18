"""Short perpetual futures right after a pump, using real perp prices and real funding.
Signal: 1h perp candle up > JUMP with quote volume > 5x its 72h median. Short the next open,
cover after 24h or at a stop (filled at the stop, or at the open if price gaps through it).
Funding: shorts receive positive rates and pay negative ones, at each settlement while open."""
import os, sys, numpy as np, pandas as pd
from pathlib import Path
from fetch_perps import base, MEME_X, DEFI
P = Path(__file__).resolve().parent / "data" / "perp"
first = pd.read_csv(P.parent / "perp_first_month.csv", index_col=0).iloc[:, 0]

def group(sym):
    b = base(sym)
    return "memes" if b in MEME_X else "defi" if b in DEFI else "new listings"

def events(d, jump=0.10, vm=5, hold=24, stop=0.30, cost=0.001):
    o, h, c, f, ts = (d[k].values for k in ("o", "h", "c", "funding", "ts"))
    r = c / o - 1
    spike = d.qv.values > vm * d.qv.rolling(72, min_periods=48).median().shift(1).values
    out, busy = [], -1
    for i in np.flatnonzero((r > jump) & spike):
        if i <= busy or i + hold + 1 >= len(d): continue
        e, x, j_exit = o[i + 1], o[i + 1 + hold], i + 1 + hold
        if stop:
            for j in range(i + 1, i + 1 + hold):
                if o[j] >= e * (1 + stop): x, j_exit = o[j], j; break
                if h[j] >= e * (1 + stop): x, j_exit = e * (1 + stop), j + 1; break
        fund = f[i + 1:j_exit].sum()
        out.append(dict(t_in=ts[i + 1], t_out=ts[j_exit], ret=(e - x) / e + fund - 2 * cost, fund=fund,
                        squeeze=h[i + 1:i + 1 + hold].max() / e - 1, age_h=i))
        busy = j_exit
    return out

def portfolio(tr, start=100.0, frac=0.10, maxpos=10):
    """Each trade: 10% of equity as notional, no leverage, max 10 open; skipped when full."""
    tr = tr.sort_values("t_in"); eq, open_, curve = start, [], []
    for _, t in tr.iterrows():
        for p in [p for p in open_ if p[0] <= t.t_in]:
            eq += p[1]; open_.remove(p); curve.append((p[0], eq))
        if len(open_) < maxpos and eq > 1:
            open_.append((t.t_out, eq * frac * t.ret))
    for p in sorted(open_): eq += p[1]; curve.append((p[0], eq))
    s = pd.Series(dict(curve)).sort_index(); s.index = pd.to_datetime(s.index, unit="ms")
    yrs = (s.index[-1] - s.index[0]).days / 365
    return s, (s.iloc[-1] / start) ** (1 / yrs) - 1, (s / s.cummax() - 1).min()

if __name__ == "__main__":
    data = {f[:-4]: pd.read_csv(P / f) for f in sorted(os.listdir(P))}
    data = {s: d for s, d in data.items() if len(d) > 200}
    print(len(data), "perps;", pd.Series([group(s) for s in data]).value_counts().to_dict(), "\n")
    for jump, stop, cost in ((0.10, 0.30, 0.001), (0.10, None, 0.001), (0.10, 0.15, 0.001), (0.10, 0.30, 0.002), (0.05, 0.30, 0.001)):
        rows = [dict(sym=s, grp=group(s), **e) for s, d in data.items() for e in events(d, jump, stop=stop, cost=cost)]
        tr = pd.DataFrame(rows); tr["year"] = pd.to_datetime(tr.t_in, unit="ms").dt.year
        print(f"=== pump >{jump*100:.0f}%/1h, stop {stop}, cost {cost*100:.1f}%/side ===")
        for g, x in tr.groupby("grp"):
            by = x.groupby("year").ret.mean().mul(100).round(1).to_dict()
            print(f"  {g:13s} n={len(x):5d} avg {x.ret.mean()*100:+5.2f}% median {x.ret.median()*100:+5.2f}% won {(x.ret>0).mean()*100:3.0f}% "
                  f"funding/trade {x.fund.mean()*100:+5.2f}% worst {x.ret.min()*100:5.0f}% | by year {by}")
        young = tr.age_h < 168
        print(f"  first week after perp launch: n={young.sum()} avg {tr.ret[young].mean()*100:+.2f}% | after: n={(~young).sum()} avg {tr.ret[~young].mean()*100:+.2f}%")
        s, cagr, dd = portfolio(tr)
        print(f"  ACCOUNT SIM $100, 10%/trade, no leverage: final ${s.iloc[-1]:,.0f}  CAGR {cagr*100:.0f}%  max DD {dd*100:.0f}%  "
              f"({s.index[0].date()} -> {s.index[-1].date()})")
        yearly = s.groupby(s.index.year).agg(lambda v: v.iloc[-1]); print("  year-end equity:", yearly.round(0).to_dict(), "\n")
