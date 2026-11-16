"""Run one variant on one split with baselines."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .backtest import run_backtest
from .strategy import make_signals
from .stats import summarize, buy_and_hold, daily_returns
from .costs import BASE
from .config import split_bounds, SEED, HOLDOUT_GUARD
from .data import HoldoutAccessError


def bounds(split: str, final_holdout: bool = False):
    a, b = split_bounds(split)
    if b > HOLDOUT_GUARD and not final_holdout:
        raise HoldoutAccessError("holdout split requires --final-holdout")
    return a, b


def run(df1, f, fund, p: dict, split: str, mult: float = 1.0, final_holdout: bool = False) -> pd.DataFrame:
    a, b = bounds(split, final_holdout)
    sig = make_signals(f, p)
    return run_backtest(df1, fund, sig, a, b, BASE.scaled(mult), mode=1 if "limit_off_atr" in p else 0,
                        limit_win=p.get("limit_win", 30))


def random_baseline(df1, f, fund, p: dict, trades: pd.DataFrame, split: str, mult: float = 1.0,
                    n_sims: int = 300, final_holdout: bool = False, seed: int = SEED) -> dict:
    """Random entries with the same stop/target/time-stop rule, the same number of trades, the same
    long/short mix and the same hour-of-day distribution as the strategy."""
    a, b = bounds(split, final_holdout)
    n = len(trades)
    if n == 0:
        return dict(rand_mean=np.nan, rand_p95=np.nan, rand_p=np.nan)
    rng = np.random.default_rng(seed)
    base = make_signals(f, {**p, "event": "pd_sweep", "event_kw": {}, "flip": 1, "bias": None, "side": None,
                            "hours": (0, 24)})   # only used for stop/target columns
    base = base[(base.index >= a) & (base.index < b) & np.isfinite(base["stop_dist"]) & (base["stop_dist"] > 0)]
    hours = trades["signal_time"].dt.hour.to_numpy()
    by_hour = {h: np.where(base.index.hour == h)[0] for h in range(24)}
    long_share = float((trades["dir"] > 0).mean())
    means = np.empty(n_sims)
    for k in range(n_sims):
        pick = np.array([rng.choice(by_hour[h]) for h in hours])
        pick = np.unique(pick)
        s = base.iloc[pick].copy()
        s["dir"] = np.where(rng.random(len(s)) < long_share, 1, -1)
        t = run_backtest(df1, fund, s, a, b, BASE.scaled(mult), mode=1 if "limit_off_atr" in p else 0,
                         limit_win=p.get("limit_win", 30))
        means[k] = t["R"].mean() if len(t) else np.nan
    obs = trades["R"].mean()
    return dict(rand_mean=float(np.nanmean(means)), rand_p95=float(np.nanpercentile(means, 95)),
                rand_p=float((np.sum(means >= obs) + 1) / (n_sims + 1)))


def full_eval(df1, f, fund, p, split, mult=1.0, final_holdout=False, n_sims=300):
    a, b = bounds(split, final_holdout)
    t = run(df1, f, fund, p, split, mult, final_holdout)
    s = summarize(t, a, b)
    if s["n"]:
        s.update(random_baseline(df1, f, fund, p, t, split, mult, n_sims, final_holdout))
        bh = buy_and_hold(df1, fund, a, b)
        s.update(bh_ret_pct=bh["ret_pct"], bh_sharpe=bh["sharpe"], bh_max_dd_pct=bh["max_dd_pct"])
        dr = daily_returns(t, a, b)
        # buy-and-hold scaled to the strategy's daily volatility ("same risk")
        s["bh_ret_pct_volmatched"] = float(bh["daily_mean"] * (dr.std() / bh["daily_vol"]) * len(dr) * 100) if bh["daily_vol"] > 0 else np.nan
        s["strat_ret_pct_simple"] = float(dr.mean() * len(dr) * 100)
    return t, s
