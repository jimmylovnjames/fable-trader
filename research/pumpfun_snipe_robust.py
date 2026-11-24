"""Robustness of the sniping result: take-profit triggered on candle CLOSES instead of highs (highs include bad
prints and the exact peak is rarely fillable), plus a stratified bootstrap 95% interval. Cached candles only."""
import io, contextlib, runpy, numpy as np, pandas as pd
from gecko import ohlcv
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("pumpfun_snipe.py", run_name="not_main")
pop, sample, FEE, FIXED = g["pop"], g["sample"], g["FEE"], g["FIXED"]
w = pop.stratum.value_counts(normalize=True)

def run(L, tp_on, tp=2.0, sl=0.5, minutes=30):
    if L is None: return None
    if len(L) == 0: return -2 * FEE - FIXED
    entry, t_in = L[0, 4], L[0, 0]
    for t, o, h, l, cl, v in L[1:]:
        if t > t_in + minutes * 60: break
        if (h if tp_on == "high" else cl) >= tp * entry: return (tp if tp_on == "high" else cl / entry) * (1 - FEE) ** 2 - 1 - FIXED
        if cl <= sl * entry: return cl / entry * (1 - FEE) ** 2 - 1 - FIXED
    k = np.searchsorted(L[:, 0], t_in + minutes * 60, side="right") - 1
    return L[max(k, 0), 4] / entry * (1 - FEE) ** 2 - 1 - FIXED

rng = np.random.default_rng(0)
for tp_on in ("high", "close"):
    r = pd.DataFrame([(x.stratum, run(ohlcv(x.bonding_curve, "minute", 1, 1000, token=x.mint), tp_on)) for x in sample.itertuples()],
                     columns=["s", "ret"]).dropna()
    groups = {s: gg.ret.values for s, gg in r.groupby("s", observed=True)}
    est = sum(w[s] * v.mean() for s, v in groups.items())
    bs = [sum(w[s] * rng.choice(v, len(v)).mean() for s, v in groups.items()) for _ in range(5000)]
    print(f"buy end of minute 1, TP +100% on {tp_on:5s}: avg {est*100:+.1f}% per trade, 95% CI [{np.percentile(bs,2.5)*100:+.1f}%, {np.percentile(bs,97.5)*100:+.1f}%]")
