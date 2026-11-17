"""Rejected idea: buy dips / sell bounces on small tokens (hourly, 2023-now).
Result: ~63% win rate but ~0% average gross edge; negative on every token at retail fees.
Run: python research/range_trading.py   (downloads ~22 tokens of hourly data, ~10 min first time)"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
DATA = ROOT / "data"
import requests, time, pandas as pd, numpy as np, os
U="https://data-api.binance.vision/api/v3/klines"
SYMS=["POL","ARB","OP","SUI","SEI","TIA","INJ","NEAR","APT","FET","RENDER","GALA","CHZ","SAND","ALGO","VET","HBAR","ATOM","DOT","ADA","DOGE","LINK"]
def get(s):
    (DATA/"hourly").mkdir(parents=True,exist_ok=True); f=DATA/"hourly"/f"{s}.csv"
    if os.path.exists(f): return pd.read_csv(f,index_col=0,parse_dates=True)
    rows=[];since=int(pd.Timestamp("2023-01-01",tz="UTC").timestamp()*1000)
    while True:
        r=requests.get(U,params=dict(symbol=s+"USDT",interval="1h",startTime=since,limit=1000),timeout=30)
        if r.status_code!=200: print(s,r.status_code,r.text[:80]); return None
        b=r.json()
        if not b: break
        rows+=b; since=b[-1][0]+3600000
        if len(b)<1000: break
    d=pd.DataFrame([x[:5] for x in rows],columns=["ts","o","h","l","c"]).astype(float)
    d.index=pd.to_datetime(d.pop("ts"),unit="ms",utc=True); d.to_csv(f); return d
def trades(d, k=2.0, n=20, er_max=0.15, er_n=100, exit="mid", stop=None, maxhold=72):
    c,o=d.c.values,d.o.values
    ma=d.c.rolling(n).mean().values; sd=d.c.rolling(n).std().values
    er=(d.c.diff(er_n).abs()/d.c.diff().abs().rolling(er_n).sum()).values  # low = choppy/ranging
    out=[];i=max(n,er_n)+1;N=len(c)
    while i<N-1:
        if c[i]<ma[i]-k*sd[i] and (er_max is None or er[i]<er_max):
            e=o[i+1]; j=i+1
            while j<N-1:
                tgt=ma[j] if exit=="mid" else ma[j]+k*sd[j]
                if c[j]>=tgt or (stop and c[j]<=e*(1-stop)) or j-i>=maxhold: break
                j+=1
            x=o[j+1] if j+1<N else c[j]
            out.append((d.index[i],x/e-1,j-i)); i=j+1
        else: i+=1
    return out
data={s:get(s) for s in SYMS}; data={s:d for s,d in data.items() if d is not None and len(d)>5000}
print(len(data),"tokens",{s:str(d.index[0].date()) for s,d in data.items()})
def report(name,**kw):
    allr=[];per={}
    for s,d in data.items():
        t=trades(d,**kw); r=np.array([x[1] for x in t]); per[s]=r; allr+=t
    r=np.array([x[1] for x in allr]); hold=np.mean([x[2] for x in allr])
    line=f"{name:44s} n={len(r):5d} win {np.mean(r>0)*100:4.0f}% gross/trade {r.mean()*100:+.2f}% med {np.median(r)*100:+.2f}% worst {r.min()*100:+.0f}% hold {hold:.0f}h |"
    for cost in (0.001,0.003,0.005):
        net=r-2*cost; prof=sum(1 for s in per if len(per[s]) and (per[s]-2*cost).sum()>0)
        line+=f" net@{cost*100:.1f}%/side {net.mean()*100:+.2f}% ({prof}/{len(per)} tokens +)"
    print(line); return allr
a=report("dip in range -> sell at average")
report("dip in range -> sell at upper band",exit="top")
report("same, 8% stop-loss",stop=0.08)
report("no range filter (any dip)",er_max=None)
report("deeper dip (3 sd)",k=3.0)
report("slower bands (n=50)",n=50,er_n=200)
df=pd.DataFrame(a,columns=["t","r","h"]).set_index("t"); df["net"]=df.r-0.01
print(df.groupby(df.index.year).net.agg(["count","mean","sum"]).round(4))
