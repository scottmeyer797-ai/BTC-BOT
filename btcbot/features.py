"""Causal feature construction on 5-minute bars.

Convention: row with index t (bar OPEN time) describes the bar [t, t+5m) and every column uses only
information available at the bar CLOSE (t+5m).  A signal on row t is executed at the open of the
1-minute bar that starts at t+5m, never earlier.  tests/test_lookahead.py verifies causality by
truncation: features at row t must not change when all data after t+5m is removed.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from numba import njit
from .data import resample

BAR = "5min"
N_DAY = 288  # 5m bars per day


def true_range(h, l, c):
    pc = c.shift(1)
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


@njit(cache=True)
def _equal_levels(high, low, atr, lookback, wing, tol):
    """For each bar i return (eq_high_level, eq_low_level) or nan.
    eq_high_level: highest confirmed pivot high in [i-lookback, i-wing-1] such that at least one more
    confirmed pivot high lies within tol*ATR below it and no bar in the window before i traded above it."""
    n = len(high)
    piv_h = np.zeros(n, np.bool_); piv_l = np.zeros(n, np.bool_)
    for j in range(wing, n - wing):
        ok_h = True; ok_l = True
        for k in range(j - wing, j + wing + 1):
            if high[k] > high[j]: ok_h = False
            if low[k] < low[j]: ok_l = False
        piv_h[j] = ok_h; piv_l[j] = ok_l
    eh = np.full(n, np.nan); el = np.full(n, np.nan)
    for i in range(lookback + 1, n):
        a = atr[i - 1]
        if not a > 0:
            continue
        lo_i = i - lookback
        # highs
        L = -1.0; mx = -1.0
        for j in range(lo_i, i):
            if high[j] > mx: mx = high[j]
            if j <= i - wing - 1 and piv_h[j] and high[j] > L: L = high[j]
        if L > 0 and mx <= L:
            cnt = 0
            for j in range(lo_i, i - wing):
                if piv_h[j] and L - high[j] <= tol * a: cnt += 1
            if cnt >= 2: eh[i] = L
        # lows
        L = 1e18; mn = 1e18
        for j in range(lo_i, i):
            if low[j] < mn: mn = low[j]
            if j <= i - wing - 1 and piv_l[j] and low[j] < L: L = low[j]
        if L < 1e17 and mn >= L:
            cnt = 0
            for j in range(lo_i, i - wing):
                if piv_l[j] and low[j] - L <= tol * a: cnt += 1
            if cnt >= 2: el[i] = L
    return eh, el


def build_features(df1: pd.DataFrame, oi: pd.Series | None = None) -> pd.DataFrame:
    b = resample(df1, BAR)
    f = b[["open", "high", "low", "close", "volume"]].copy()
    f["filled"] = b["filled"] > 0
    f["zero_vol"] = b["volume"] <= 0
    f["delta"] = 2 * b["taker_buy_volume"] - b["volume"]
    f["delta_frac"] = (f["delta"] / b["volume"]).where(b["volume"] > 0, 0.0)
    f["ret"] = np.log(f["close"]).diff()
    f["range"] = f["high"] - f["low"]
    f["tr"] = true_range(f["high"], f["low"], f["close"])
    f["atr"] = f["tr"].rolling(14).mean()                 # includes current bar
    f["atr_prev"] = f["atr"].shift(1)                     # excludes current bar
    f["atr_slow"] = f["tr"].rolling(N_DAY).mean()
    f["sigma_prev"] = f["ret"].rolling(N_DAY).std().shift(1)
    f["rv_day"] = f["ret"].rolling(N_DAY).std()           # 24h realised vol of 5m returns
    f["vol_med_prev"] = f["volume"].rolling(N_DAY).median().shift(1)
    f["vol_ratio"] = f["volume"] / f["vol_med_prev"]
    f["hh_prev"] = f["high"].rolling(48).max().shift(1)   # 4h structure, excluding current bar
    f["ll_prev"] = f["low"].rolling(48).min().shift(1)
    f["close_pos"] = ((f["close"] - f["low"]) / f["range"]).where(f["range"] > 0, 0.5)

    # previous UTC-day high/low (known from 00:00 of the current day)
    day = f.index.floor("D")
    dh = f["high"].groupby(day).max(); dl = f["low"].groupby(day).min()
    f["pdh"] = dh.shift(1).reindex(day).to_numpy()
    f["pdl"] = dl.shift(1).reindex(day).to_numpy()
    # Asia session range (00:00-07:00 UTC), usable from 07:00 UTC the same day
    hour = f.index.hour
    asia = hour < 7
    ah = f["high"].where(asia).groupby(day).max(); al = f["low"].where(asia).groupby(day).min()
    f["asia_high"] = np.where(~asia, ah.reindex(day).to_numpy(), np.nan)
    f["asia_low"] = np.where(~asia, al.reindex(day).to_numpy(), np.nan)
    f["prev_close"] = f["close"].shift(1)

    eh, el = _equal_levels(f["high"].to_numpy(), f["low"].to_numpy(), f["atr"].to_numpy(), 96, 3, 0.25)
    f["eq_high"] = eh; f["eq_low"] = el

    # higher-timeframe (1H) bias from COMPLETED 1H bars only
    h1 = resample(df1, "1h")
    ema = h1["close"].ewm(span=50, adjust=False, min_periods=50).mean()
    bias = np.sign(h1["close"] - ema)
    slope = np.sign(ema - ema.shift(6))
    known = (h1.index + pd.Timedelta(hours=1))            # time at which the 1H bar is complete
    t_close = f.index + pd.Timedelta(minutes=5)
    for name, s in (("h1_bias", bias), ("h1_slope", slope)):
        ss = pd.Series(s.to_numpy(), index=known)
        f[name] = ss.reindex(t_close, method="ffill").to_numpy()
    h1ret = np.log(h1["close"]).diff()
    f["h1_ret_prev"] = pd.Series(h1ret.to_numpy(), index=known).reindex(t_close, method="ffill").to_numpy()

    # 1H displacement (completed 1H bars): range > 2.5 x ATR1h(14, prior), close in outer quartile,
    # close beyond prior 24h high/low. Placed on the 5m row whose close coincides with the 1H close.
    tr1 = true_range(h1["high"], h1["low"], h1["close"]); atr1 = tr1.rolling(14).mean().shift(1)
    rng1 = h1["high"] - h1["low"]; pos1 = ((h1["close"] - h1["low"]) / rng1).where(rng1 > 0, 0.5)
    up = (rng1 > 2.5 * atr1) & (pos1 >= 0.75) & (h1["close"] > h1["high"].rolling(24).max().shift(1))
    dn = (rng1 > 2.5 * atr1) & (pos1 <= 0.25) & (h1["close"] < h1["low"].rolling(24).min().shift(1))
    d1 = pd.Series(up.astype(int) - dn.astype(int)).to_numpy()
    f["h1_disp"] = pd.Series(d1, index=known - pd.Timedelta(minutes=5)).reindex(f.index).fillna(0).astype("int8").to_numpy()
    f["h1_atr"] = pd.Series(tr1.rolling(14).mean().to_numpy(), index=known).reindex(t_close, method="ffill").to_numpy()

    h1d = (2 * h1["taker_buy_volume"] - h1["volume"]) / h1["volume"].where(h1["volume"] > 0)
    f["h1_delta_frac"] = pd.Series(h1d.to_numpy(), index=known).reindex(t_close, method="ffill").to_numpy()

    if oi is not None:
        # snapshot stamped at bar close (t+5m) vs snapshot at bar open (t).  NOTE: assumes the OI
        # snapshot stamped t+5m is observable at t+5m (live: REST poll). Flagged as an assumption.
        oi = oi.where(oi > 0)
        o_close = oi.reindex(t_close).to_numpy(); o_open = oi.reindex(f.index).to_numpy()
        f["oi_chg"] = o_close / o_open - 1.0
        o_lag = oi.reindex(f.index - pd.Timedelta(minutes=5)).to_numpy()
        f["oi_chg_lag"] = o_open / o_lag - 1.0              # strictly lagged alternative
        o_1h = oi.reindex(t_close - pd.Timedelta(hours=1)).to_numpy()
        f["oi_chg_1h"] = o_close / o_1h - 1.0               # OI change over the hour ending at bar close
    return f
