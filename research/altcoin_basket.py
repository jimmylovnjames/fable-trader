"""Trend bot on altcoins vs BTC+ETH, 2018-now, incl. a point-in-time top-N universe
with delisted coins (LUNA, FTT, ...) to avoid survivorship bias.
Result: alt baskets ~8-13% CAGR vs ~30% for BTC+ETH, same ~-46% drawdowns.
Run: python research/altcoin_basket.py   (downloads ~775 pairs of daily data, ~5 min first time)"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
DATA = ROOT / "data"
import os, re, warnings, numpy as np, pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
warnings.filterwarnings("ignore")
from fabletrader.config import Config
from fabletrader.engine import plan_orders
from fabletrader.backtest import stats

def load():
    if not (DATA / "daily").exists(): fetch_universe()
    O,C,V={}, {}, {}
    for f in os.listdir(DATA / "daily"):
        d=pd.read_csv(DATA / "daily" / f)
        if len(d)<30: continue
        d.index=pd.to_datetime(d.ts,unit="ms",utc=True); s=f[:-8]  # strip USDT.csv
        O[s],C[s],V[s]=d.o,d.c,d.qv
    p=(pd.DataFrame(O),pd.DataFrame(C),pd.DataFrame(V))
    cut=pd.Timestamp.now("UTC").normalize()-pd.Timedelta(days=1)
    p=tuple(x.loc[:cut] for x in p)  # completed bars only
    return p

def fetch_universe():
    """Daily klines for every Binance USDT pair, delisted ones included."""
    U = "https://data-api.binance.vision/api/v3"
    out = DATA / "daily"; out.mkdir(parents=True, exist_ok=True)
    syms = [s["symbol"] for s in requests.get(U + "/exchangeInfo", timeout=60).json()["symbols"] if s["quoteAsset"] == "USDT"]
    def get(sym):
        f = out / f"{sym}.csv"
        if f.exists(): return
        rows, since = [], 1500000000000
        while True:
            r = requests.get(U + "/klines", params=dict(symbol=sym, interval="1d", startTime=since, limit=1000), timeout=30)
            b = r.json() if r.status_code == 200 else []
            if not b: break
            rows += b; since = b[-1][0] + 86400000
            if len(b) < 1000: break
        pd.DataFrame([[x[0], x[1], x[4], x[7]] for x in rows], columns=["ts", "o", "c", "qv"]).astype(float).to_csv(f, index=False)
    with ThreadPoolExecutor(8) as ex: list(ex.map(get, syms))

O,C,V=load()
STABLE={"USDC","BUSD","TUSD","USDP","PAX","DAI","UST","FDUSD","USDS","USDSB","SUSD","AEUR","EUR","GBP","AUD","EURI","USD1","PYUSD","BFUSD","XUSD","RLUSD","USDE","PAXG","WBTC","WBETH","BETH","BKRW","IDRT","BIDR","TRY","BRL","RUB","NGN","UAH","ZAR","XAUT","FRAX","LUSD","GUSD","USTC","U","USDT"}
lev=re.compile(r".+(UP|DOWN|BULL|BEAR)$")
vol=C.pct_change(fill_method=None).rolling(90,min_periods=60).std().median()*np.sqrt(365)
alts=[s for s in C if s not in STABLE|{"BTC","ETH"} and not lev.match(s) and (vol.get(s,0)>0.25)]
print("candidate alts:",len(alts), "| excluded as stable/low-vol:",[s for s in C if s not in alts and s not in STABLE and not lev.match(s)][:15])

# splice renamed tokens so the hand-picked basket has full history
def splice(new,old):
    for M in (O,C):
        M[new]=M[new].combine_first(M[old].where(M.index<M[new].first_valid_index()))
splice("POL","MATIC"); splice("RENDER","RNDR")
for M in (O,C,V): M.drop(columns=["MATIC","RNDR"],inplace=True,errors="ignore")
alts=[a for a in alts if a not in ("MATIC","RNDR")]

def weights(closes, cfg, n):
    score=sum((closes>closes.rolling(w).mean()).astype(float) for w in cfg.trend_windows)/len(cfg.trend_windows)
    v=closes.pct_change(fill_method=None).rolling(cfg.vol_window).std()*np.sqrt(365)
    w=(score*(cfg.target_vol/v).clip(upper=1)/n)
    ready=closes.rolling(max(cfg.trend_windows)).count()>=max(cfg.trend_windows)
    return w.where(ready & v.notna(),0.0).fillna(0.0)

def universe_mask(cols, top):
    """point-in-time: each month, top-N by trailing 30d median quote volume among coins with 210+ days history"""
    qv=V[cols].rolling(30,min_periods=20).median(); age=C[cols].notna().cumsum()
    m=pd.DataFrame(False,index=C.index,columns=cols)
    for d in C.index[C.index.is_month_start]:
        elig=qv.loc[d][(age.loc[d]>=210)&C.loc[d].notna()].dropna()
        m.loc[d,elig.nlargest(top).index]=True
    firsts=m.index.is_month_start
    m=m.where(pd.Series(firsts,index=m.index),np.nan).ffill().fillna(False).astype(bool)
    return m

def backtest(cols, cfg, n, cash=100.0, cost=0.007, mask=None, start="2018-03-01"):
    w=weights(C[cols],cfg,n)
    if mask is not None: w=w.where(mask,0.0)
    w=w.loc[start:]; o=O[cols].loc[start:]; c=C[cols].loc[start:]
    lastc=C[cols].ffill().loc[start:]
    qty={}; eq=[]; trades=0; forced=0
    for i in range(1,len(c)):
        px=o.iloc[i]
        for a in list(qty):          # delisted: dump at last close -5%
            if np.isnan(px[a]):
                cash+=qty.pop(a)*lastc.iloc[i-1][a]*0.95*(1-cost); forced+=1
        tgt=w.iloc[i-1]; tgt=tgt[(tgt>0)&px.notna()]
        names=set(qty)|set(tgt.index)
        q={a:qty.get(a,0.0) for a in names}; p={a:float(px[a]) for a in names}
        for od in plan_orders(cash,q,p,tgt.to_dict(),cfg,cost):
            if od.side=="sell": cash+=od.quote*(1-cost); qty[od.asset]-=od.qty
            else: cash-=od.quote*(1+cost); qty[od.asset]=qty.get(od.asset,0)+od.qty
            trades+=1
        qty={a:v for a,v in qty.items() if v>1e-12}
        cc=lastc.iloc[i]
        eq.append(cash+sum(v*cc[a] for a,v in qty.items()))
    e=pd.Series(eq,index=c.index[1:])
    return e, trades/(len(e)/365), forced

def bench(cols, mask=None, start="2018-03-01"):
    r=C[cols].pct_change(fill_method=None).loc[start:]
    if mask is not None: r=r.where(mask.shift(1).loc[start:].fillna(False).astype(bool))
    return (1+r.mean(axis=1).fillna(0)).cumprod()*100

def line(name,e,extra=""):
    s=stats(e); yr=e.groupby(e.index.year).agg(lambda x:x.iloc[-1]/x.iloc[0]-1)
    print(f"{name:34s} final {e.iloc[-1]:9.0f} CAGR {s['cagr']*100:6.1f}% vol {s['vol']*100:5.1f}% Sharpe {s['sharpe']:5.2f} maxDD {s['max_drawdown']*100:6.1f}% {extra}")
    return yr

BASKET="POL ARB OP SUI SEI TIA INJ NEAR APT FET RENDER GALA CHZ SAND ALGO VET HBAR ATOM DOT ADA DOGE LINK".split()
years={}
print("\n=== all runs: $10,000 start, cost 0.7%/side alts (Kraken 0.4% + 0.3% slippage), 0.5% BTC/ETH ===")
cfg2=Config(rebalance_band=0.10); e,t,_=backtest(["BTC","ETH"],cfg2,2,10000,0.005)
years["BTC+ETH bot"]=line("BTC+ETH bot (current)",e,f"trades/yr {t:.0f}")
years["BTC+ETH hold"]=line("BTC+ETH buy&hold",bench(["BTC","ETH"]))

cfgB=Config(rebalance_band=0.2/22)
e,t,_=backtest(BASKET,cfgB,22,10000)
years["22 picked, bot"]=line("A) your 22 tokens, trend bot",e,f"trades/yr {t:.0f}")
years["22 picked, hold"]=line("A) your 22 tokens, buy&hold",bench(BASKET))

for top in (20,50):
    m=universe_mask(alts,top); cfgU=Config(rebalance_band=0.2/top)
    e,t,f=backtest(alts,cfgU,top,10000,mask=m)
    years[f"top{top} bot"]=line(f"B) top-{top} alts point-in-time, bot",e,f"trades/yr {t:.0f} forced delist sales {f}")
    years[f"top{top} hold"]=line(f"B) top-{top} alts, buy&hold",bench(alts,m))
    if top==20: e20=e
print("\nyear-by-year:"); print((pd.DataFrame(years)*100).round(0).to_string())

print("\n=== account size (top-20 alts bot, min order $10) ===")
m=universe_mask(alts,20)
for cash in (100,500,1000,10000):
    e,t,_=backtest(alts,Config(rebalance_band=0.01),20,cash,mask=m); line(f"start ${cash}",e,f"trades/yr {t:.0f}")

print("\n=== fee sensitivity and blending ===")
m=universe_mask(alts,20)
eb,_,_=backtest(["BTC","ETH"],Config(rebalance_band=0.10),2,10000,0.005)
for cost in (0.004,0.002):
    e,_,_=backtest(BASKET,Config(rebalance_band=0.2/22),22,10000,cost); line(f"A) 22 tokens @ {cost*100:.1f}%/side",e)
    e,_,_=backtest(alts,Config(rebalance_band=0.01),20,10000,cost,mask=m); line(f"B) top-20 @ {cost*100:.1f}%/side",e)
ea,_,_=backtest(alts,Config(rebalance_band=0.01),20,10000,mask=m)
ra,rb=ea.pct_change().dropna(),eb.pct_change().dropna()
print("daily return correlation, BTC+ETH bot vs alt bot:",round(ra.corr(rb),2))
for wa in (0.0,0.2,0.5):  # daily-rebalanced blend
    r=(1-wa)*rb+wa*ra; line(f"blend {int((1-wa)*100)}% BTC+ETH / {int(wa*100)}% alts",(1+r).cumprod()*10000)
