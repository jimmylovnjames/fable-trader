"""Trend-following with volatility targeting.

For each asset, on completed daily closes only:
  trend score = fraction of SMA windows the close is above (0..1)
  vol scale   = min(1, target_vol / realised_vol)
  weight      = score * vol_scale / n_assets
Total weight is capped at max_exposure. Long-only, never leveraged.

The point is not prediction. It is to hold crypto while it is trending up and
sit in cash through the long drawdowns, which is where small accounts die.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config

ANNUALISE = np.sqrt(365)


def target_weights(closes: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """closes: daily close per asset (columns), completed bars only.

    Returns the target weight per asset for each day, computed from data up to
    and including that day's close. Trade it on the *next* bar.
    """
    score = sum((closes > closes.rolling(w).mean()).astype(float) for w in cfg.trend_windows)
    score = score / len(cfg.trend_windows)
    vol = closes.pct_change().rolling(cfg.vol_window).std() * ANNUALISE
    scale = (cfg.target_vol / vol).clip(upper=1.0)
    w = score * scale / closes.shape[1]
    # not enough history -> stay out
    ready = closes.rolling(max(cfg.trend_windows)).count() >= max(cfg.trend_windows)
    w = w.where(ready & vol.notna(), 0.0).fillna(0.0)
    total = w.sum(axis=1)
    over = total > cfg.max_exposure
    w.loc[over] = w.loc[over].div(total[over], axis=0) * cfg.max_exposure
    return w


def latest_weights(closes: pd.DataFrame, cfg: Config) -> dict[str, float]:
    return target_weights(closes, cfg).iloc[-1].to_dict()
