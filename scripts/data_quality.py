#!/usr/bin/env python3
"""Data-quality report -> reports/data_quality.md.  Usage: python scripts/data_quality.py [--final-holdout]"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from btcbot import data
from btcbot.config import REPORTS

ap = argparse.ArgumentParser(); ap.add_argument("--final-holdout", action="store_true"); a = ap.parse_args()
fh = a.final_holdout
L = ["# Data quality report" + (" (incl. holdout)" if fh else " (train+validation only)"), ""]
for mk in ("fut", "spot"):
    raw = data.load_klines(mk, raw=True, final_holdout=fh)
    dup = int(raw["open_time"].duplicated().sum())
    df = data.load_klines(mk, final_holdout=fh)
    n, miss = len(df), int(df["filled"].sum())
    L += [f"## {mk} 1m klines", f"- range: {df.index[0]} .. {df.index[-1]}, grid minutes: {n:,}",
          f"- duplicate rows: {dup}", f"- missing minutes (filled flat, flagged): {miss:,} ({miss/n:.4%})"]
    f = df["filled"].to_numpy()
    # contiguous gap runs
    d = np.diff(np.r_[0, f.astype(int), 0]); s = np.where(d == 1)[0]; e = np.where(d == -1)[0]
    runs = sorted(zip(e - s, df.index[s]), reverse=True)[:15]
    L += [f"- number of gap runs: {len(s)}; longest:"] + [f"  - {t}: {k} min" for k, t in runs]
    real = df[~df["filled"]]
    zv = int((real["volume"] == 0).sum())
    bad = int(((real["high"] < real[["open", "close"]].max(axis=1)) | (real["low"] > real[["open", "close"]].min(axis=1))).sum())
    r = np.log(real["close"]).diff().abs()
    L += [f"- zero-volume real bars: {zv:,}", f"- OHLC-inconsistent bars: {bad}",
          f"- largest 1m |log return|: {r.max():.4f} at {r.idxmax()}",
          f"- taker_buy_volume > volume rows: {int((real['taker_buy_volume'] > real['volume'] * (1+1e-9)).sum())}", ""]
fu = data.load_funding(final_holdout=fh)
gaps = fu.index.to_series().diff().dt.total_seconds().div(3600)
L += ["## funding", f"- {len(fu)} prints {fu.index[0]} .. {fu.index[-1]}",
      f"- interval hours value counts: {gaps.value_counts().to_dict()}",
      f"- mean {fu.mean()*1e4:.3f} bps/8h, min {fu.min()*1e4:.1f}, max {fu.max()*1e4:.1f}", ""]
m = data.load_metrics(final_holdout=fh)
full = pd.date_range(m.index[0], m.index[-1], freq="5min")
miss = full.difference(m.index)
L += ["## metrics (open interest, 5m)", f"- {len(m):,} rows {m.index[0]} .. {m.index[-1]}",
      f"- missing 5m snapshots: {len(miss):,} ({len(miss)/len(full):.3%})",
      f"- days with >=1 missing snapshot: {len(set(miss.date))}; days fully missing: {int((pd.Series(1, index=miss).groupby(miss.date).sum() >= 288).sum())}",
      f"- null oi rows: {int(m['oi'].isna().sum())}", ""]
(REPORTS / ("data_quality_holdout.md" if fh else "data_quality.md")).write_text("\n".join(L))
print("\n".join(L))
