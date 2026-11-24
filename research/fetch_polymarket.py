"""Resolved Polymarket binary markets (every 4th day since 2025-01, >= $10k volume, random 10k sample) + hourly YES price for the
10 days before each market's scheduled end (or close, if earlier)."""
import json, time, requests, pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
OUT = Path(__file__).resolve().parent / "data" / "poly"; OUT.mkdir(parents=True, exist_ok=True)
G, C = "https://gamma-api.polymarket.com/markets", "https://clob.polymarket.com/prices-history"

def markets(sample=10000, seed=0):
    """Every 4th day since 2025-01-01, all resolved binary markets with >= $10k volume; random sample."""
    f = OUT / "markets.csv"
    if f.exists(): return pd.read_csv(f)
    rows = []
    for day in pd.date_range("2025-01-01", pd.Timestamp.now().normalize() - pd.Timedelta(days=2), freq="4D"):
        off = 0
        while off < 2100:
            for t in range(5):
                try:
                    r = requests.get(G, params=dict(closed="true", limit=100, offset=off, volume_num_min=10000,
                                                    end_date_min=day.isoformat() + "Z", end_date_max=(day + pd.Timedelta(days=1)).isoformat() + "Z"), timeout=60)
                    if r.status_code == 200: break
                except Exception: pass
                time.sleep(2 ** t)
            b = r.json() if r.status_code == 200 else []
            if not b: break
            for m in b:
                try:
                    outs, px, toks = json.loads(m["outcomes"]), json.loads(m["outcomePrices"]), json.loads(m["clobTokenIds"])
                except Exception: continue
                if len(outs) != 2 or sorted(px) != ["0", "1"]: continue  # resolved binary only
                rows.append(dict(id=m["id"], q=m["question"], slug=m.get("slug"), end=m["endDate"], closed=m.get("closedTime"),
                                 start=m.get("startDate"), vol=m["volumeNum"], fees=m.get("feesEnabled"), neg=m.get("negRisk"),
                                 tok0=toks[0], out0=outs[0], won0=int(px[0] == "1")))
            off += 100
        print(day.date(), len(rows), flush=True)
    df = pd.DataFrame(rows).drop_duplicates("id")
    df.to_csv(OUT / "markets_all.csv", index=False)
    df = df.sample(min(sample, len(df)), random_state=seed)
    df.to_csv(f, index=False); return df

def hist(row):
    f = OUT / "h" / f"{row.id}.csv"
    if f.exists(): return
    end = min(pd.Timestamp(row.end), pd.Timestamp(row.closed) if isinstance(row.closed, str) else pd.Timestamp(row.end))
    end = int(end.timestamp())
    for t in range(5):
        try:
            r = requests.get(C, params=dict(market=row.tok0, startTs=end - 10 * 86400 + 60, endTs=end, fidelity=60), timeout=60)
            if r.status_code == 200: break
        except Exception: pass
        time.sleep(2 ** t)
    h = r.json().get("history", []) if r.status_code == 200 else []
    pd.DataFrame(h).to_csv(f, index=False)

if __name__ == "__main__":
    df = markets(); print(len(df), "resolved binary markets", flush=True)
    (OUT / "h").mkdir(exist_ok=True)
    t = time.time()
    with ThreadPoolExecutor(12) as ex: list(ex.map(hist, df.itertuples()))
    print("done in", round(time.time() - t), "s")
