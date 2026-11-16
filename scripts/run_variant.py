#!/usr/bin/env python3
"""Run a registered variant and append the result to reports/variants.csv.
  python scripts/run_variant.py V01 --split train
  python scripts/run_variant.py V01 --split validation
  python scripts/run_variant.py V01 --split holdout --final-holdout   # ONCE, frozen strategy only
"""
import sys, argparse, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from btcbot.panel import load_panel
from btcbot.variants import VARIANTS
from btcbot.evaluate import full_eval
from btcbot.config import REPORTS

ap = argparse.ArgumentParser()
ap.add_argument("ids", nargs="+"); ap.add_argument("--split", default="train")
ap.add_argument("--mults", default="1.0,1.5"); ap.add_argument("--final-holdout", action="store_true")
ap.add_argument("--sims", type=int, default=300); ap.add_argument("--no-log", action="store_true")
a = ap.parse_args()
df1, f, fund = load_panel(final_holdout=a.final_holdout)
out = REPORTS / "variants.csv"
rows = []
for vid in a.ids:
    p = VARIANTS[vid]
    for m in [float(x) for x in a.mults.split(",")]:
        t, s = full_eval(df1, f, fund, p, a.split, m, a.final_holdout, a.sims)
        (REPORTS / "trades").mkdir(exist_ok=True)
        t.to_csv(REPORTS / "trades" / f"{vid}_{a.split}_{m}.csv", index=False)
        rows.append(dict(variant=vid, split=a.split, mult=m, **s, params=json.dumps(p)))
r = pd.DataFrame(rows)
if not a.no_log:
    old = pd.read_csv(out) if out.exists() else pd.DataFrame()
    if len(old):
        old = old[~(old["variant"].isin(r["variant"]) & (old["split"] == a.split))]
    pd.concat([old, r], ignore_index=True).to_csv(out, index=False)
cols = ["variant", "split", "mult", "n", "exp_R", "ci90_lo", "ci90_hi", "pf", "win_rate", "max_dd_pct", "sharpe", "q_prof",
        "long_n", "long_exp", "short_n", "short_exp", "cost_R", "rand_mean", "rand_p", "bh_sharpe", "avg_hold_min", "avg_risk_bps"]
pd.set_option("display.width", 300)
print(r[[c for c in cols if c in r]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
