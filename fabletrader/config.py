"""Configuration: defaults, overridden by config.yaml, secrets from env/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class Config:
    # --- market ---
    exchange: str = "kraken"            # any ccxt exchange id
    quote: str = "USD"                  # quote currency you fund the account with
    assets: list[str] = field(default_factory=lambda: ["BTC", "ETH"])
    # --- strategy (daily bars, long-only, no leverage) ---
    trend_windows: list[int] = field(default_factory=lambda: [20, 50, 100, 200])
    vol_window: int = 30                # days of returns for realised vol
    target_vol: float = 0.60            # annualised vol each asset sleeve is scaled to
    max_exposure: float = 1.0           # cap on total invested fraction of equity
    rebalance_band: float = 0.10        # only trade when weight is off by this much
    # --- risk ---
    max_drawdown: float = 0.50          # kill switch: flatten + halt beyond this
    # --- execution ---
    min_order_quote: float = 10.0       # never send orders smaller than this
    paper_start_cash: float = 100.0
    paper_fee: float = 0.004            # 0.40% taker, Kraken's lowest tier
    paper_slippage: float = 0.001
    state_file: str = "state.json"

    def symbol(self, asset: str) -> str:
        return f"{asset}/{self.quote}"

    @property
    def symbols(self) -> list[str]:
        return [self.symbol(a) for a in self.assets]

    @property
    def warmup(self) -> int:
        return max(max(self.trend_windows), self.vol_window) + 1


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: str | Path = "config.yaml") -> Config:
    cfg = Config()
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
        known = {f.name for f in fields(Config)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        for k, v in raw.items():
            setattr(cfg, k, v)
    if not 0 < cfg.max_exposure <= 1:
        raise ValueError("max_exposure must be in (0, 1] - this bot never uses leverage")
    if not cfg.assets:
        raise ValueError("assets must not be empty")
    return cfg
