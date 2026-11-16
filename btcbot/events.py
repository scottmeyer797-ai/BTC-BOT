"""Exact definitions of the 'institutional footprint' events (Phase 0).

Each function takes the 5m feature frame and returns an int8 Series `dir` on the same index:
+1 = hypothesised long, -1 = hypothesised short, 0 = no event.  The event is known at the close of
the bar (index + 5min).  Directions encode the pre-registered hypothesis in research_log.md.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _mk(f, short, long):
    d = pd.Series(0, index=f.index, dtype="int8")
    d[long.fillna(False)] = 1
    d[short.fillna(False)] = -1
    d[(long.fillna(False) & short.fillna(False))] = 0
    d[f["filled"] | f["zero_vol"]] = 0
    return d


def e1_pd_sweep(f):
    """Sweep of previous UTC-day high/low and close back inside -> fade."""
    s = (f["high"] > f["pdh"]) & (f["close"] < f["pdh"]) & (f["prev_close"] < f["pdh"])
    l = (f["low"] < f["pdl"]) & (f["close"] > f["pdl"]) & (f["prev_close"] > f["pdl"])
    return _mk(f, s, l)


def e2_asia_sweep(f):
    """Sweep of the Asia-session (00-07 UTC) high/low during 07-21 UTC, close back inside -> fade."""
    h = f.index.hour
    win = (h >= 7) & (h < 21)
    s = win & (f["high"] > f["asia_high"]) & (f["close"] < f["asia_high"]) & (f["prev_close"] < f["asia_high"])
    l = win & (f["low"] < f["asia_low"]) & (f["close"] > f["asia_low"]) & (f["prev_close"] > f["asia_low"])
    return _mk(f, s, l)


def e3_equal_raid(f):
    """Raid of equal highs/lows (>=2 pivot highs within 0.25 ATR in the last 8h, untouched) with a
    close back below/above the level -> fade."""
    s = (f["high"] > f["eq_high"]) & (f["close"] < f["eq_high"])
    l = (f["low"] < f["eq_low"]) & (f["close"] > f["eq_low"])
    return _mk(f, s, l)


def e4_displacement(f, k=2.5):
    """Displacement bar: range > k*ATR(14, prior bars), closes in the outer 25% of its range and
    closes beyond the prior 4h high/low (structure break) -> continuation."""
    big = f["range"] > k * f["atr_prev"]
    l = big & (f["close_pos"] >= 0.75) & (f["close"] > f["hh_prev"])
    s = big & (f["close_pos"] <= 0.25) & (f["close"] < f["ll_prev"])
    return _mk(f, s, l)


def e5_cascade(f, z=3.0, v=3.0, oi_drop=None, oi_col="oi_chg"):
    """Liquidation-cascade proxy: 5m return beyond z*sigma(24h), volume > v x 24h median volume and
    aggressive flow in the direction of the move -> fade (bounce after forced flow).
    oi_drop: additionally require open interest to fall by at least this fraction during the bar."""
    zs = f["ret"] / f["sigma_prev"]
    hot = f["vol_ratio"] > v
    l = (zs < -z) & hot & (f["delta_frac"] < -0.05)
    s = (zs > z) & hot & (f["delta_frac"] > 0.05)
    if oi_drop is not None:
        ok = f[oi_col] <= -oi_drop
        l &= ok; s &= ok
    return _mk(f, s, l)


def e6_delta_div(f):
    """Delta divergence at a 4h extreme: bar makes a new 4h high and closes up but net aggressive
    flow is selling (delta_frac < -0.05) -> fade; mirrored at lows."""
    s = (f["high"] > f["hh_prev"]) & (f["close"] > f["open"]) & (f["delta_frac"] < -0.05)
    l = (f["low"] < f["ll_prev"]) & (f["close"] < f["open"]) & (f["delta_frac"] > 0.05)
    return _mk(f, s, l)


def _open_drive(f, tz, hh, mm, thr=1.0):
    """Direction of the first 30 minutes after a cash-market open (local exchange time, DST-aware,
    weekdays). Event at open+30m if |30m return| > thr * sigma_5m * sqrt(6) -> continuation."""
    loc = f.index.tz_convert(tz)
    first = (loc.hour == hh) & (loc.minute == mm) & (loc.dayofweek < 5)
    last = np.roll(first, 5)  # the 6th bar of the 30-minute window
    last[:5] = False
    r30 = np.log(f["close"] / f["open"].shift(5))
    strong = r30.abs() > thr * f["sigma_prev"].shift(5) * np.sqrt(6)
    return _mk(f, last & strong & (r30 < 0), last & strong & (r30 > 0))


def e7a_ny_open_drive(f):
    return _open_drive(f, "America/New_York", 9, 30)


def e7b_london_open_drive(f):
    return _open_drive(f, "Europe/London", 8, 0)


def e1t_pd_sweep_with_bias(f):
    """E1 restricted to sweeps against the 1H trend (sweep of PDL while 1H close > EMA50 -> long)."""
    d = e1_pd_sweep(f)
    return d.where(d == f["h1_bias"], 0).astype("int8")


def e2r_asia_break_follow(f):
    """Data-driven reversal of E2 (the sweep bar is followed, not faded)."""
    return (-e2_asia_sweep(f)).astype("int8")


def e4h_h1_displacement(f):
    d = f["h1_disp"].copy()
    d[f["filled"] | f["zero_vol"]] = 0
    return d.astype("int8")


EVENTS_0B = {
    "E5c_cascade_z4_v5_oi1.0_fade": lambda f: e5_cascade(f, z=4, v=5, oi_drop=0.010),
    "E5d_cascade_z5_v5_oi1.5_fade": lambda f: e5_cascade(f, z=5, v=5, oi_drop=0.015),
    "E5e_cascade_oi_drop_LAGGED_fade": lambda f: e5_cascade(f, oi_drop=0.005, oi_col="oi_chg_lag"),
    "E5b_cascade_oi_drop_fade(long horizons)": lambda f: e5_cascade(f, oi_drop=0.005),
    "E1t_pd_sweep_fade_with_1h_bias": e1t_pd_sweep_with_bias,
    "E2r_asia_sweep_FOLLOW": e2r_asia_break_follow,
    "E4h_1h_displacement_follow": e4h_h1_displacement,
}

EVENTS = {
    "E1_pd_sweep_fade": e1_pd_sweep,
    "E2_asia_sweep_fade": e2_asia_sweep,
    "E3_equal_hl_raid_fade": e3_equal_raid,
    "E4_displacement_follow": e4_displacement,
    "E5_cascade_fade": e5_cascade,
    "E5b_cascade_oi_drop_fade": lambda f: e5_cascade(f, oi_drop=0.005),
    "E6_delta_divergence_fade": e6_delta_div,
    "E7a_ny_open_drive_follow": e7a_ny_open_drive,
    "E7b_london_open_drive_follow": e7b_london_open_drive,
}
