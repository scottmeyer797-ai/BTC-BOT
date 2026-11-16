"""Strategy = event + optional filters + fixed stop / fixed reward:risk / time stop.

`make_signals` is the single signal generator used by the backtest AND the forward-test harness.
Stops are k_stop x ATR(1H, 14 completed bars) at signal time; target = rr x stop.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import events as ev

EVENT_FUNCS = {
    "cascade": ev.e5_cascade,
    "pd_sweep": lambda f: ev.e1_pd_sweep(f),
    "asia_sweep": lambda f: ev.e2_asia_sweep(f),
    "eq_raid": lambda f: ev.e3_equal_raid(f),
    "displacement": ev.e4_displacement,
    "delta_div": lambda f: ev.e6_delta_div(f),
    "h1_disp": lambda f: ev.e4h_h1_displacement(f),
    "trend_sweep": lambda f: ev.trend_sweep(f),
    "h1_disp_oi": ev.h1_disp_oi,
    "cascade_reclaim": ev.cascade_reclaim,
    "h1_disp_lead": ev.h1_disp_lead,
}


def make_signals(f: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Returns a frame indexed by ENTRY time (= signal bar close = next 1m bar open)."""
    raw = EVENT_FUNCS[p["event"]](f, **p.get("event_kw", {}))
    stop_px = raw.attrs.get("stop_px")
    d = raw.astype("int64")
    d = d * p.get("flip", 1)
    if p.get("bias") == "with":        # trade only in the direction of the 1H trend
        d = d.where(d == f["h1_bias"], 0)
    elif p.get("bias") == "against":
        d = d.where(d == -f["h1_bias"], 0)
    if p.get("side") == "long":
        d = d.where(d > 0, 0)
    elif p.get("side") == "short":
        d = d.where(d < 0, 0)
    if "hours" in p:                   # UTC hour window [a, b) of the signal bar close
        a, b = p["hours"]
        hc = (f.index + pd.Timedelta(minutes=5)).hour
        d = d.where((hc >= a) & (hc < b), 0)
    stop = p["k_stop"] * f["h1_atr"]
    if stop_px is not None:            # structural stop with a floor of k_stop x ATR(1H)
        stop = np.maximum((f["close"] - stop_px).abs() + 0.1 * f["atr"], stop)
    out = pd.DataFrame({"dir": d.fillna(0).astype("int64").to_numpy(),
                        "stop_dist": stop.to_numpy(),
                        "tgt_dist": (p["rr"] * stop).to_numpy(),
                        "max_hold": int(p["max_hold"])},
                       index=f.index + pd.Timedelta(minutes=5))
    if "limit_off_atr" in p:           # limit entry offset in units of ATR(1H)
        out["limit_off"] = (p["limit_off_atr"] * f["h1_atr"]).to_numpy()
    out.loc[~np.isfinite(out["stop_dist"]) | (out["stop_dist"] <= 0), "dir"] = 0
    return out
