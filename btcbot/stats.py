"""Performance statistics, bootstrap CIs, baselines, deflated Sharpe."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats as ss
from .config import SEED, session_of_hour


def boot_ci(x, n=10000, lo=5, hi=95, seed=SEED):
    x = np.asarray(x, float)
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), size=(n, len(x)))].mean(1)
    return float(np.percentile(m, lo)), float(np.percentile(m, hi))


def block_boot_ci(t: pd.DataFrame, n=5000, lo=5, hi=95, seed=SEED):
    """Bootstrap of mean R resampling whole ISO weeks (keeps within-week dependence)."""
    if len(t) < 2:
        return (np.nan, np.nan)
    wk = t["entry_time"].dt.strftime("%G-%V")
    g = t.groupby(wk)["R"].agg(["sum", "count"])
    S, C = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(S), size=(n, len(S)))
    m = S[idx].sum(1) / C[idx].sum(1)
    return float(np.percentile(m, lo)), float(np.percentile(m, hi))


def equity_curve(t: pd.DataFrame) -> pd.Series:
    eq = (1 + t["eq_ret"]).cumprod()
    return pd.Series(eq.to_numpy(), index=pd.DatetimeIndex(t["exit_time"]))


def daily_returns(t: pd.DataFrame, start, end) -> pd.Series:
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D", tz="UTC")
    if len(t) == 0:
        return pd.Series(0.0, index=days)
    r = np.log1p(t["eq_ret"]).groupby(t["exit_time"].dt.floor("D")).sum()
    return np.expm1(r.reindex(days, fill_value=0.0))


def max_drawdown(eq: np.ndarray) -> float:
    eq = np.r_[1.0, eq]
    return float((1 - eq / np.maximum.accumulate(eq)).max())


def longest_losing_streak(r: np.ndarray) -> int:
    best = cur = 0
    for v in r:
        cur = cur + 1 if v <= 0 else 0
        best = max(best, cur)
    return best


def summarize(t: pd.DataFrame, start, end) -> dict:
    n = len(t)
    if n == 0:
        return dict(n=0)
    R = t["R"].to_numpy()
    wins, losses = R[R > 0].sum(), -R[R <= 0].sum()
    dr = daily_returns(t, start, end)
    sd = dr.std()
    downside = np.sqrt((np.minimum(dr, 0) ** 2).mean())
    lo, hi = boot_ci(R)
    blo, bhi = block_boot_ci(t)
    q = t.groupby(t["exit_time"].dt.tz_localize(None).dt.to_period("Q"))["R"].sum()
    eq = (1 + t["eq_ret"]).cumprod().to_numpy()
    return dict(n=n, exp_R=float(R.mean()), ci90_lo=lo, ci90_hi=hi, blk_ci90_lo=blo, blk_ci90_hi=bhi,
                win_rate=float((R > 0).mean()), pf=float(wins / losses) if losses > 0 else np.inf,
                total_R=float(R.sum()), ret_pct=float((eq[-1] - 1) * 100), max_dd_pct=max_drawdown(eq) * 100,
                sharpe=float(dr.mean() / sd * np.sqrt(365)) if sd > 0 else np.nan,
                sortino=float(dr.mean() / downside * np.sqrt(365)) if downside > 0 else np.nan,
                lose_streak=longest_losing_streak(R), q_prof=float((q > 0).mean()), n_q=len(q),
                avg_hold_min=float(t["hold_min"].mean()), avg_risk_bps=float(t["risk"].mean() * 1e4),
                cost_R=float((t["R_gross"] - t["R"]).mean()),
                long_n=int((t["dir"] > 0).sum()), long_exp=float(t.loc[t["dir"] > 0, "R"].mean()) if (t["dir"] > 0).any() else np.nan,
                short_n=int((t["dir"] < 0).sum()), short_exp=float(t.loc[t["dir"] < 0, "R"].mean()) if (t["dir"] < 0).any() else np.nan,
                sr_trade=float(R.mean() / R.std(ddof=1)) if n > 1 and R.std() > 0 else np.nan)


def by_group(t: pd.DataFrame, how: str) -> pd.DataFrame:
    if how == "year":
        g = t["entry_time"].dt.year
    elif how == "quarter":
        g = t["exit_time"].dt.tz_localize(None).dt.to_period("Q").astype(str)
    elif how == "session":
        g = t["entry_time"].dt.hour.map(session_of_hour)
    elif how == "side":
        g = t["dir"].map({1: "long", -1: "short"})
    elif how == "reason":
        g = t["reason"]
    x = t.groupby(g)["R"].agg(n="count", exp_R="mean", total_R="sum", win_rate=lambda s: (s > 0).mean())
    return x


def buy_and_hold(df1: pd.DataFrame, funding: pd.Series, start, end) -> dict:
    """Long 1x BTCUSDT perp from start to end incl. funding paid; daily stats."""
    c = df1["close"][(df1.index >= start) & (df1.index < end)].resample("1D").last()
    r = c.pct_change().dropna()
    f = funding[(funding.index >= start) & (funding.index < end)].resample("1D").sum().reindex(r.index, fill_value=0.0)
    r = r - f
    eq = (1 + r).cumprod().to_numpy()
    return dict(ret_pct=float((eq[-1] - 1) * 100), sharpe=float(r.mean() / r.std() * np.sqrt(365)),
                max_dd_pct=max_drawdown(eq) * 100, daily_vol=float(r.std()), daily_mean=float(r.mean()))


def deflated_sharpe(sr: float, n_obs: int, skew: float, kurt: float, n_trials: int, var_sr_trials: float) -> dict:
    """Bailey & Lopez de Prado (2014). sr = per-observation Sharpe (not annualised); kurt = raw kurtosis."""
    emc = 0.5772156649
    n_trials = max(int(n_trials), 2)
    sr0 = np.sqrt(var_sr_trials) * ((1 - emc) * ss.norm.ppf(1 - 1 / n_trials) + emc * ss.norm.ppf(1 - 1 / (n_trials * np.e)))
    den = np.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    z = (sr - sr0) * np.sqrt(n_obs - 1) / den
    return dict(sr0=float(sr0), dsr=float(ss.norm.cdf(z)), psr0=float(ss.norm.cdf(sr * np.sqrt(n_obs - 1) / den)))
