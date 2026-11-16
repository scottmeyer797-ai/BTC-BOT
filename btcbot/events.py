"""Exact definitions of the 'institutional footprint' events (Phase 0).

Each function takes the 5m feature frame and returns an int8 Series `dir` on the same index:
+1 = hypothesised long, -1 = hypothesised short, 0 = no event.  The event is known at the close of
the bar (index + 5min).  Directions encode the pre-registered hypothesis in research_log.md.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def _reclaim(casc, o, h, l, c, window):
    """After a cascade bar (casc=+1 means flush DOWN, we look for longs) wait up to `window` bars for
    the first bar that closes in our direction AND beyond the previous bar's extreme. Returns the
    direction and the structural stop price (extreme of the flush so far)."""
    n = len(c)
    d = np.zeros(n, np.int8); stop = np.full(n, np.nan)
    side = 0; ext = 0.0; left = 0
    for i in range(1, n):
        if side != 0 and casc[i] == 0:
            if side > 0:
                ext = min(ext, l[i])
                if c[i] > o[i] and c[i] > h[i - 1]:
                    d[i] = 1; stop[i] = ext; side = 0
            else:
                ext = max(ext, h[i])
                if c[i] < o[i] and c[i] < l[i - 1]:
                    d[i] = -1; stop[i] = ext; side = 0
            left -= 1
            if left <= 0:
                side = 0
        if casc[i] != 0:              # (re)arm on every cascade bar
            if casc[i] == side:
                ext = min(ext, l[i]) if side > 0 else max(ext, h[i])
            else:
                side = casc[i]; ext = l[i] if side > 0 else h[i]
            left = window
    return d, stop


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


def trend_sweep(f):
    """Liquidity raid against the 1H trend: in an up-trend (1H close > EMA50) a 5m bar trades below
    the prior 4h low and closes back above it -> long. Mirrored for down-trends."""
    l = (f["h1_bias"] > 0) & (f["low"] < f["ll_prev"]) & (f["close"] > f["ll_prev"])
    s = (f["h1_bias"] < 0) & (f["high"] > f["hh_prev"]) & (f["close"] < f["hh_prev"])
    return _mk(f, s, l)


def h1_disp_oi(f, oi_sign=1):
    """1H displacement with open interest rising (oi_sign=+1: new positions, initiative flow) or
    falling (oi_sign=-1: position closing / squeeze) during the displacement hour."""
    d = e4h_h1_displacement(f)
    ok = (np.sign(f["oi_chg_1h"]) == oi_sign)
    return d.where(ok, 0).astype("int8")


def cascade_reclaim(f, z=3.0, v=3.0, oi_drop=0.005, window=12):
    """Cascade (E5 family) followed within `window` 5m bars by a reclaim bar. Sets f-aligned
    attribute `stop_px` (structural stop = extreme of the flush) on the returned Series."""
    casc = e5_cascade(f, z=z, v=v, oi_drop=oi_drop)
    d, stop = _reclaim(casc.to_numpy(), f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(),
                       f["close"].to_numpy(), window)
    out = pd.Series(d, index=f.index, dtype="int8")
    out[f["filled"] | f["zero_vol"]] = 0
    out.attrs["stop_px"] = pd.Series(stop, index=f.index)
    return out


def h1_disp_k(f, k=2.5):
    """Parametrised 1H displacement (k=2.5 reproduces e4h_h1_displacement)."""
    big = f["h1_range_atr"] > k
    l = big & (f["h1_pos"] >= 0.75) & (f["h1_brk"] > 0)
    s = big & (f["h1_pos"] <= 0.25) & (f["h1_brk"] < 0)
    return _mk(f, s, l)


def h1_disp_lead_k(f, lead="spot", k=2.5):
    d = h1_disp_k(f, k)
    x = d * np.sign(f["h1_prem_chg"])
    ok = (x < 0) if lead == "spot" else (x > 0)
    return d.where(ok, 0).astype("int8")


def h1_disp_lead(f, lead="spot"):
    """1H displacement split by who led: 'spot' = perp premium fell during an up-move (rose during a
    down-move), i.e. spot moved further than the perp; 'perp' = the opposite (leverage-led)."""
    d = e4h_h1_displacement(f)
    x = d * np.sign(f["h1_prem_chg"])
    ok = (x < 0) if lead == "spot" else (x > 0)
    return d.where(ok, 0).astype("int8")


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
