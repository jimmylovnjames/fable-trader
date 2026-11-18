"""Hourly perpetual-futures klines + funding history from Binance's public archive (data.binance.vision)
for meme, DeFi and post-2024 USDT-margined perps."""
import io, re, time, zipfile, requests, pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fetch_hourly import MEME, DEFI
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
B = "https://data.binance.vision/"
OUT = Path(__file__).resolve().parent / "data" / "perp"; OUT.mkdir(parents=True, exist_ok=True)
MEME_X = MEME + "POPCAT MOODENG GOAT CHILLGUY SPX FARTCOIN MOG BRETT MEW PONKE MYRO BOB WOJAK".split()

def base(sym):
    return re.sub(r"^(1000000|1000|1M)", "", sym[:-4])

def ls(prefix, pat):
    out, marker = [], ""
    while True:
        r = requests.get(S3, params={"delimiter": "/", "prefix": prefix, "marker": marker}, timeout=60).text
        found = re.findall(pat, r); out += found
        if "<IsTruncated>true" not in r or not found: return out
        marker = re.findall(r"<(?:Key|Prefix)>([^<]+)</(?:Key|Prefix)>", r)[-1]

def grab(key):
    for t in range(5):
        try:
            r = requests.get(B + key, timeout=60)
            if r.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                return pd.read_csv(z.open(z.namelist()[0]), header=None, skiprows=1 if b"open_time" in z.read(z.namelist()[0])[:40] or b"calc_time" in z.read(z.namelist()[0])[:40] else 0)
            if r.status_code == 404: return None
        except Exception: pass
        time.sleep(2 ** t)

def fetch(sym):
    f = OUT / f"{sym}.csv"
    if f.exists(): return
    ks = [k for k in ls(f"data/futures/um/monthly/klines/{sym}/1h/", r"<Key>([^<]+\.zip)</Key>") if k[-11:-4] >= "2023-01"]
    kl = [x for x in map(grab, ks) if x is not None]
    if not kl: return
    k = pd.concat(kl).iloc[:, [0, 1, 2, 3, 4, 7]]; k.columns = ["ts", "o", "h", "l", "c", "qv"]
    fk = [x for x in map(grab, [k_.replace("/klines/", "/fundingRate/").replace("/1h/", "/").replace("-1h-", "-fundingRate-") for k_ in ks]) if x is not None]
    k = k.astype(float).sort_values("ts").drop_duplicates("ts")
    k["funding"] = 0.0
    if fk:
        fr = pd.concat(fk).iloc[:, [0, 2]].astype(float); fr.columns = ["t", "rate"]
        hour = (fr.t // 3_600_000 * 3_600_000)
        k = k.set_index("ts"); k.loc[k.index.intersection(hour), "funding"] = fr.groupby(hour).rate.sum().reindex(k.index.intersection(hour)).values
        k = k.reset_index()
    k.to_csv(f, index=False)

if __name__ == "__main__":
    syms = [s for s in ls("data/futures/um/monthly/klines/", r"<Prefix>data/futures/um/monthly/klines/([^/]+)/</Prefix>") if s.endswith("USDT")]
    print(len(syms), "USDT perps listed", flush=True)
    def first_month(s):
        ks = ls(f"data/futures/um/monthly/klines/{s}/1h/", r"<Key>([^<]+\.zip)</Key>")
        return ks[0][-11:-4] if ks else None
    with ThreadPoolExecutor(16) as ex: firsts = dict(zip(syms, ex.map(first_month, syms)))
    uni = [s for s in syms if base(s) in MEME_X or base(s) in DEFI or (firsts[s] and firsts[s] >= "2024-01")]
    pd.Series(firsts).to_csv(OUT.parent / "perp_first_month.csv")
    print(len(uni), "in universe", flush=True)
    t = time.time()
    with ThreadPoolExecutor(16) as ex: list(ex.map(fetch, uni))
    print("done in", round(time.time() - t), "s;", len(list(OUT.iterdir())), "files")
