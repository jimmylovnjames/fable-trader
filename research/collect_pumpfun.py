"""Record every new pump.fun coin for a while. The API lists only the newest ~1,050 coins (~45 min),
so polling every 3 minutes captures each coin's state from birth until it ages out of the list."""
import json, time, sys, requests, pandas as pd
from pathlib import Path
B = "https://frontend-api-v3.pump.fun/coins"
OUT = Path(__file__).resolve().parent / "data" / "pump"; OUT.mkdir(parents=True, exist_ok=True)
KEEP = ("mint", "symbol", "bonding_curve", "creator", "created_timestamp", "complete", "market_cap", "usd_market_cap",
        "ath_market_cap", "ath_market_cap_timestamp", "quote_mint", "program", "last_trade_timestamp", "pool_address", "pump_swap_pool", "raydium_pool")

def page(off):
    for t in range(4):
        try:
            r = requests.get(B, params=dict(offset=off, limit=50, sort="created_timestamp", order="DESC", includeNsfw="true"), timeout=30)
            if r.status_code == 200: return r.json()
        except Exception: pass
        time.sleep(2 ** t)
    return []

if __name__ == "__main__":
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 75
    seen, t_end = {}, time.time() + minutes * 60
    while time.time() < t_end:
        now = int(time.time() * 1000); n = 0
        for off in range(0, 1050, 50):
            for c in page(off):
                rec = {k: c.get(k) for k in KEEP}; rec["seen_at"] = now
                prev = seen.get(c["mint"])
                rec["first_seen"] = prev["first_seen"] if prev else now
                seen[c["mint"]] = rec; n += 1
        pd.DataFrame(seen.values()).to_csv(OUT / "coins.csv", index=False)
        print(time.strftime("%H:%M:%S"), "polled", n, "| total coins", len(seen), flush=True)
        time.sleep(max(0, 180 - (time.time() * 1000 - now) / 1000))
