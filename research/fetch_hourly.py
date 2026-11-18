"""Hourly OHLCV for meme coins, DeFi tokens and every Binance USDT listing since 2024."""
import os, sys, time, re, requests, pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
U = "https://data-api.binance.vision/api/v3"
OUT = Path(__file__).resolve().parent / "data" / "hourly_all"; OUT.mkdir(parents=True, exist_ok=True)
MEME = "DOGE SHIB PEPE FLOKI BONK WIF BOME MEME TURBO NEIRO PNUT ACT PEOPLE 1000SATS ORDI TRUMP PENGU DOGS NOT BANANA 1MBABYDOGE 1000CHEEMS BROCCOLI714 TST MUBARAK".split()
DEFI = "UNI AAVE CRV COMP MKR SUSHI 1INCH DYDX LDO PENDLE GMX JUP RAY CAKE SNX ENA ETHFI JTO ONDO MORPHO EIGEN AERO".split()
STABLE = {"USDC","FDUSD","TUSD","USDP","DAI","AEUR","EUR","EURI","USD1","PYUSD","BFUSD","XUSD","RLUSD","USDE","PAXG","WBTC","WBETH","BNSOL","XAUT","USDS","U"}

def universe():
    info = requests.get(U + "/exchangeInfo", timeout=60).json()["symbols"]
    base = {s["baseAsset"] for s in info if s["quoteAsset"] == "USDT"}
    daily = Path(__file__).resolve().parent / "data" / "daily"
    new = []
    for b in base:
        f = daily / f"{b}USDT.csv"
        if b in STABLE or re.match(r".+(UP|DOWN|BULL|BEAR)$", b) or not f.exists(): continue
        d = pd.read_csv(f, nrows=1)
        if len(d) and d.ts[0] >= pd.Timestamp("2024-01-01").timestamp() * 1000: new.append(b)
    return sorted(set(MEME + DEFI + new) & base), set(new)

def get(b, start="2023-01-01"):
    f = OUT / f"{b}.csv"
    if f.exists(): return
    rows, since = [], int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    while True:
        for t in range(5):
            try:
                r = requests.get(U + "/klines", params=dict(symbol=b + "USDT", interval="1h", startTime=since, limit=1000), timeout=30)
                if r.status_code == 200: break
            except Exception: pass
            time.sleep(2 ** t)
        batch = r.json() if r.status_code == 200 else []
        if not batch: break
        rows += batch; since = batch[-1][0] + 3_600_000
        if len(batch) < 1000: break
    pd.DataFrame([[x[0], x[1], x[2], x[3], x[4], x[7]] for x in rows],
                 columns=["ts", "o", "h", "l", "c", "qv"]).astype(float).to_csv(f, index=False)

if __name__ == "__main__":
    syms, new = universe()
    print(len(syms), "symbols,", len(new), "new listings since 2024", flush=True)
    t = time.time()
    with ThreadPoolExecutor(8) as ex: list(ex.map(get, syms))
    print("done in", round(time.time() - t), "s;", len(os.listdir(OUT)), "files")
