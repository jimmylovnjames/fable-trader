"""Rate-limited, cached GeckoTerminal OHLCV fetcher (free tier ~10 calls/min)."""
import json, time, requests, numpy as np
from pathlib import Path
G = "https://api.geckoterminal.com/api/v2/networks/solana"
CACHE = Path(__file__).resolve().parent / "data" / "pump" / "candles"; CACHE.mkdir(parents=True, exist_ok=True)
_last = [0.0]

def ohlcv(pool, tf="minute", aggregate=1, limit=1000, token=None):
    """token: mint address to price (GeckoTerminal otherwise prices the pool's base token, which on PumpSwap is often SOL)."""
    f = CACHE / f"{pool}_{tf}{aggregate}_{token or 'base'}.json"
    if f.exists():
        a = np.array(json.loads(f.read_text()))
        return a[np.argsort(a[:, 0])] if len(a) else a   # GeckoTerminal returns newest-first
    for t in range(6):
        wait = 6.5 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        try:
            r = requests.get(f"{G}/pools/{pool}/ohlcv/{tf}", params=dict(aggregate=aggregate, limit=limit, currency="usd", **({"token": token} if token else {})), timeout=30)
        except Exception:
            continue
        if r.status_code == 200:
            L = r.json()["data"]["attributes"]["ohlcv_list"]; f.write_text(json.dumps(L))
            a = np.array(L); return a[np.argsort(a[:, 0])] if len(a) else a
        if r.status_code == 404:
            f.write_text("[]"); return np.array([])
        time.sleep(15 * (t + 1))  # 429 backoff
    return None
