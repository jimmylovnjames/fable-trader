"""Same sample as pumpfun_snipe.py (cached candles, no new API calls), other exit rules,
including letting winners run with no take-profit."""
import io, contextlib, runpy, numpy as np, pandas as pd
from gecko import ohlcv
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("pumpfun_snipe.py", run_name="not_main")
pop, sample, FEE, FIXED = g["pop"], g["sample"], g["FEE"], g["FIXED"]
w = pop.stratum.value_counts(normalize=True)

def run(L, entry_kind, tp, sl, minutes):
    if L is None: return None
    if len(L) == 0: return -2 * FEE - FIXED
    o0, c0 = L[0, 1], L[0, 4]
    entry = (o0 if o0 >= 0.5 * c0 else c0) if entry_kind == "seconds" else c0
    t_in = L[0, 0]
    for t, o, h, l, cl, v in (L if entry_kind == "seconds" else L[1:]):
        if t > t_in + minutes * 60: break
        if tp and h >= tp * entry: return tp * (1 - FEE) ** 2 - 1 - FIXED
        if sl and cl <= sl * entry: return cl / entry * (1 - FEE) ** 2 - 1 - FIXED
    k = np.searchsorted(L[:, 0], t_in + minutes * 60, side="right") - 1
    return L[max(k, 0), 4] / entry * (1 - FEE) ** 2 - 1 - FIXED

rules = {"TP +100% / SL -50% / 30 min": (2, 0.5, 30), "no TP, SL -50%, 30 min": (None, 0.5, 30),
         "TP +400% / SL -50% / 30 min": (5, 0.5, 30), "just hold 30 min": (None, None, 30), "just hold 5 min": (None, None, 5)}
print(f"{'exit rule':30s} {'entry':>8s}  avg/trade  wins   best")
for name, (tp, sl, mins) in rules.items():
    for ek in ("seconds", "minute"):
        res = [(x.stratum, run(ohlcv(x.bonding_curve, "minute", 1, 1000, token=x.mint), ek, tp, sl, mins)) for x in sample.itertuples()]
        r = pd.DataFrame(res, columns=["s", "ret"]).dropna()
        avg = sum(w[s] * gg.ret.mean() for s, gg in r.groupby("s", observed=True))
        won = sum(w[s] * (gg.ret > 0).mean() for s, gg in r.groupby("s", observed=True))
        print(f"{name:30s} {ek:>8s}  {avg*100:+7.1f}%  {won*100:4.0f}%  {r.ret.max()*100:+6.0f}%")
