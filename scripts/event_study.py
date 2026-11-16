#!/usr/bin/env python3
"""Phase 0 event study on TRAIN only -> reports/event_study.md, reports/event_study.csv
Usage: python scripts/event_study.py [0|0b]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from btcbot.panel import load_panel, in_split
from btcbot.events import EVENTS, EVENTS_0B
from btcbot.costs import BASE
from btcbot.config import REPORTS, SEED

PHASE = sys.argv[1] if len(sys.argv) > 1 else "0"
HORIZONS = [5, 15, 30, 60] if PHASE == "0" else [30, 60, 120, 240]
EVENTS = EVENTS if PHASE == "0" else EVENTS_0B
SUF = "" if PHASE == "0" else "_0b"
df1, f, _ = load_panel()
tr = in_split(f.index, "train")
o = f["open"]
fwd = {h: np.log(o.shift(-(1 + h // 5)) / o.shift(-1)) for h in HORIZONS}   # entry next bar open
year = f.index.year
rvq = f["rv_day"].where(tr).groupby(year).transform(lambda s: pd.qcut(s, 3, labels=False, duplicates="drop"))  # train rows only
key = pd.Series(year * 1000 + f.index.hour * 10, index=f.index) + rvq.fillna(-1)
ok = tr & rvq.notna().to_numpy()
rng = np.random.default_rng(SEED)
rows = []
for name, fn in EVENTS.items():
    d = fn(f)
    ev = (d != 0) & ok
    for h in HORIZONS:
        r = fwd[h]
        cell_mean = r[ok].groupby(key[ok]).transform("mean")           # mean fwd of ALL bars in the matched cell
        x = pd.DataFrame({"g": d[ev] * r[ev], "b": d[ev] * cell_mean.reindex(r[ev].index)}).dropna()
        x["e"] = x["g"] - x["b"]
        day = x.index.floor("D")
        grp = x.groupby(day)[["g", "e"]].agg(["sum", "count"])
        S_e, S_g, C = grp[("e", "sum")].to_numpy(), grp[("g", "sum")].to_numpy(), grp[("e", "count")].to_numpy()
        idx = rng.integers(0, len(C), size=(4000, len(C)))
        be = S_e[idx].sum(1) / C[idx].sum(1); bg = S_g[idx].sum(1) / C[idx].sum(1)
        m_e, m_g = x["e"].mean(), x["g"].mean()
        se = be.std()
        yr = x["e"].groupby(x.index.year).mean()
        rows.append(dict(event=name, horizon=h, n=len(x), n_days=len(C), long_share=float((d[ev] > 0).mean()),
                         gross_bps=m_g * 1e4, baseline_bps=x["b"].mean() * 1e4, excess_bps=m_e * 1e4,
                         ci_lo=np.percentile(be, 2.5) * 1e4, ci_hi=np.percentile(be, 97.5) * 1e4, t=m_e / se,
                         net_bps=(m_g - BASE.rt_market) * 1e4, net_ci_hi=(np.percentile(bg, 97.5) - BASE.rt_market) * 1e4,
                         cohen_d=m_e / x["e"].std(), years_same_sign=int((np.sign(yr) == np.sign(m_e)).sum()), n_years=len(yr),
                         by_year=" ".join(f"{y}:{v*1e4:+.1f}" for y, v in yr.items())))
res = pd.DataFrame(rows)
res.to_csv(REPORTS / f"event_study{SUF}.csv", index=False)
pd.set_option("display.width", 250)
show = res[["event", "horizon", "n", "gross_bps", "baseline_bps", "excess_bps", "ci_lo", "ci_hi", "t", "net_bps", "net_ci_hi", "cohen_d", "years_same_sign", "by_year"]]
md = [f"# Phase {PHASE} event study (TRAIN 2020-01-01..2024-01-31 only)", "",
      "Signed forward log-return (in hypothesis direction) from the next 5m bar open, in bps. `baseline` = mean signed return of all bars in the same (year, UTC hour, vol tercile) cell. `excess` = gross - baseline with 95% day-clustered bootstrap CI and t. `net` = gross - 12 bps round-trip taker cost; `net_ci_hi` is the upper 97.5% bound of net.", "",
      show.to_markdown(index=False, floatfmt="+.2f")]
(REPORTS / f"event_study{SUF}.md").write_text("\n".join(md))
print(show.to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
