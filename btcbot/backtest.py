"""Event-driven trade simulator on 1-minute bars. Conservative fills.

Rules (long shown; short mirrored):
  * A signal produced at the close of a 5m bar is executed on the NEXT 1m bar (index `entry_idx`).
  * Market entry: fill = open[entry_idx] * (1 + slip_mkt), taker fee.
  * Limit entry (mode 1): resting buy at L = open[entry_idx] - limit_off for `limit_win` minutes; filled
    only if a bar trades THROUGH it (low <= L - tick), at L, maker fee. If the same bar also reaches the
    stop the trade is stopped out in that bar; a target cannot fill on the fill bar.
  * Stop: if low <= stop -> fill = min(stop, bar open) * (1 - slip_stop), taker fee (gap risk included).
  * Target (limit): filled only if high >= target + tick (trade-through), at target, maker fee.
  * If stop and target are both reachable inside one bar, the STOP is assumed to have come first.
  * Time stop: after `max_hold` minutes exit at the next bar open with market slippage, taker fee.
  * Funding: every real funding print while the position is open is charged/credited on notional.
  * One position at a time; signals arriving while a position is open are skipped.
R = net return / (stop distance / reference price).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from numba import njit
from .costs import Costs, BASE, TICK, MAX_LEVERAGE, RISK_PER_TRADE

REASONS = {0: "stop", 1: "target", 2: "time", 3: "end"}


@njit(cache=True)
def _simulate(o, h, l, entry_idx, direction, stop_dist, tgt_dist, max_hold, end_idx,
              fund_cum, taker, maker, slip_mkt, slip_stop, tick, mode, limit_off, limit_win):
    n_sig = len(entry_idx)
    out = np.zeros((n_sig, 9))
    k = 0
    busy_until = -1
    for s in range(n_sig):
        i = entry_idx[s]
        if i <= busy_until or i >= end_idx - 1:
            continue
        d = direction[s]
        ref = o[i]
        fill_bar = i
        fee_in = taker
        if mode == 0:
            px_e = ref * (1.0 + d * slip_mkt)
            level = ref
        else:
            level = ref - d * limit_off[s]
            got = False
            jmax = min(i + limit_win, end_idx - 1)
            for j in range(i, jmax):
                if (d > 0 and l[j] <= level - tick) or (d < 0 and h[j] >= level + tick):
                    got = True; fill_bar = j; break
            if not got:
                continue
            px_e = level
            fee_in = maker
        stop = level - d * stop_dist[s]
        tgt = level + d * tgt_dist[s]
        last = min(fill_bar + max_hold[s], end_idx - 1)   # bar at whose open a time exit happens
        reason = 2
        px_x = 0.0; fee_out = taker; j_exit = last
        done = False
        for j in range(fill_bar, last):
            if d > 0:
                if l[j] <= stop:
                    px_x = min(stop, o[j]) * (1.0 - slip_stop); reason = 0; j_exit = j; done = True; break
                if h[j] >= tgt + tick and not (mode == 1 and j == fill_bar):
                    px_x = tgt; fee_out = maker; reason = 1; j_exit = j; done = True; break
            else:
                if h[j] >= stop:
                    px_x = max(stop, o[j]) * (1.0 + slip_stop); reason = 0; j_exit = j; done = True; break
                if l[j] <= tgt - tick and not (mode == 1 and j == fill_bar):
                    px_x = tgt; fee_out = maker; reason = 1; j_exit = j; done = True; break
        if not done:
            px_x = o[last] * (1.0 - d * slip_mkt)
            if last == end_idx - 1 and last < fill_bar + max_hold[s]:
                reason = 3
        # funding prints with fill_bar <= t <= j_exit  (fund_cum[i] = sum of rates at minutes < i)
        funding = d * (fund_cum[j_exit + 1] - fund_cum[fill_bar])
        gross = d * (px_x - px_e) / px_e
        net = gross - fee_in - fee_out * (px_x / px_e) - funding
        risk = stop_dist[s] / level
        out[k, 0] = s; out[k, 1] = fill_bar; out[k, 2] = j_exit; out[k, 3] = px_e; out[k, 4] = px_x
        out[k, 5] = reason; out[k, 6] = gross; out[k, 7] = net; out[k, 8] = risk
        k += 1
        busy_until = j_exit
    return out[:k]


def run_backtest(df1: pd.DataFrame, funding: pd.Series, signals: pd.DataFrame,
                 start: pd.Timestamp, end: pd.Timestamp, costs: Costs = BASE,
                 mode: int = 0, limit_win: int = 30) -> pd.DataFrame:
    """signals: index = entry time (1m bar open at which the order is sent), columns dir, stop_dist,
    tgt_dist, max_hold [, limit_off]. Only signals with start <= entry time < end are traded and all
    positions are force-closed at `end`."""
    idx = df1.index
    s = signals[(signals.index >= start) & (signals.index < end) & (signals["dir"] != 0)]
    s = s[np.isfinite(s["stop_dist"]) & (s["stop_dist"] > 0) & np.isfinite(s["tgt_dist"])]
    e_idx = idx.get_indexer(s.index)
    assert (e_idx >= 0).all()
    end_idx = int(idx.searchsorted(end))
    fr = np.zeros(len(idx) + 2)
    fpos = idx.get_indexer(funding.index[funding.index <= idx[-1]])
    fr[fpos[fpos >= 0]] = funding.to_numpy()[: len(fpos)][fpos >= 0]
    fund_cum = np.concatenate([[0.0], np.cumsum(fr)])
    m = costs.mult
    lo = s["limit_off"].to_numpy(float) if "limit_off" in s else np.zeros(len(s))
    out = _simulate(df1["open"].to_numpy(), df1["high"].to_numpy(), df1["low"].to_numpy(),
                    e_idx.astype(np.int64), s["dir"].to_numpy(np.int64), s["stop_dist"].to_numpy(float),
                    s["tgt_dist"].to_numpy(float), s["max_hold"].to_numpy(np.int64), end_idx, fund_cum,
                    costs.taker * m, costs.maker * m, costs.slip_mkt * m, costs.slip_stop * m, TICK,
                    mode, lo, limit_win)
    t = pd.DataFrame(out, columns=["sig", "fill_bar", "exit_bar", "entry_px", "exit_px", "reason", "gross", "net", "risk"])
    si = t["sig"].astype(int).to_numpy()
    t["signal_time"] = s.index[si]
    t["entry_time"] = idx[t["fill_bar"].astype(int)]
    t["exit_time"] = idx[t["exit_bar"].astype(int)]
    t["dir"] = s["dir"].to_numpy()[si]
    t["reason"] = t["reason"].astype(int).map(REASONS)
    t["R"] = t["net"] / t["risk"]
    t["R_gross"] = t["gross"] / t["risk"]
    t["leverage"] = np.minimum(RISK_PER_TRADE / t["risk"], MAX_LEVERAGE)
    t["eq_ret"] = t["leverage"] * t["net"]            # account return of the trade at 1% risk, leverage-capped
    t["hold_min"] = t["exit_bar"] - t["fill_bar"]
    return t.drop(columns=["sig"])
