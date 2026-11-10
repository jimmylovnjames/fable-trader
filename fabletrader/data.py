"""Market data. History for backtests comes from Binance's public data mirror
(no account, no key); live candles come from the trading exchange via ccxt."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

BINANCE = "https://data-api.binance.vision/api/v3/klines"
DAY_MS = 86_400_000


def fetch_history(asset: str, start: str = "2017-01-01", cache_dir: str = "data") -> pd.DataFrame:
    """Daily OHLC for ASSET/USDT, completed bars only, cached on disk per day."""
    cache = Path(cache_dir) / f"{asset}USDT_1d_{pd.Timestamp.now('UTC'):%Y%m%d}.csv"
    if cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    rows, since = [], int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    while True:
        r = requests.get(BINANCE, timeout=30, params={
            "symbol": f"{asset}USDT", "interval": "1d", "startTime": since, "limit": 1000})
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + DAY_MS
        if len(batch) < 1000:
            break
        time.sleep(0.2)
    df = pd.DataFrame([r[:5] for r in rows], columns=["ts", "open", "high", "low", "close"]).astype(float)
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    df = df[df.index + pd.Timedelta(days=1) <= pd.Timestamp.now("UTC")]  # drop the forming bar
    cache.parent.mkdir(exist_ok=True)
    df.to_csv(cache)
    return df


def make_exchange(exchange_id: str, auth: bool = False):
    import ccxt

    params = {"enableRateLimit": True}
    if auth:
        key, secret = os.environ.get("EXCHANGE_API_KEY"), os.environ.get("EXCHANGE_API_SECRET")
        if not key or not secret:
            raise SystemExit("live mode needs EXCHANGE_API_KEY and EXCHANGE_API_SECRET (env or .env)")
        params |= {"apiKey": key, "secret": secret}
        if os.environ.get("EXCHANGE_API_PASSWORD"):
            params["password"] = os.environ["EXCHANGE_API_PASSWORD"]
    ex = getattr(ccxt, exchange_id)(params)
    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca:  # ccxt ignores the env CA bundle; needed behind TLS-inspecting proxies
        ex.validateServerSsl = ca
    return ex


def live_closes(ex, symbols: list[str], bars: int) -> pd.DataFrame:
    """Completed daily closes for each symbol from the exchange."""
    now = pd.Timestamp.now("UTC")
    out = {}
    for s in symbols:
        o = ex.fetch_ohlcv(s, "1d", limit=bars + 2)
        ser = pd.Series({pd.Timestamp(r[0], unit="ms", tz="UTC"): float(r[4]) for r in o})
        out[s] = ser[ser.index + pd.Timedelta(days=1) <= now]
    df = pd.DataFrame(out).dropna()
    if len(df) < bars:
        raise RuntimeError(f"{ex.id} returned {len(df)} daily bars, need {bars}")
    return df
