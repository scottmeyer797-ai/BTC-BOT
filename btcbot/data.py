"""Data loading with a hard holdout guard.

Nothing at or after the validation end (2025-06-01) can be loaded unless final_holdout=True is
passed explicitly (CLI flag --final-holdout). Raw month files for the holdout are also not
downloaded before the freeze step, so the guard is enforced twice.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import DATA, HOLDOUT_GUARD, SPLITS, ts


class HoldoutAccessError(RuntimeError):
    pass


def _check_end(end: pd.Timestamp, final_holdout: bool) -> None:
    if end > HOLDOUT_GUARD and not final_holdout:
        raise HoldoutAccessError(
            f"Requested data up to {end} which is inside the final holdout (>= {HOLDOUT_GUARD}). "
            "Pass final_holdout=True / --final-holdout only at the freeze step.")


def _months(folder: str, end: pd.Timestamp) -> list:
    files = sorted((DATA / folder).glob("*.parquet"))
    last_month = (end - pd.Timedelta(minutes=1)).strftime("%Y-%m")
    return [f for f in files if f.stem <= last_month]


def default_end(final_holdout: bool) -> pd.Timestamp:
    return ts(SPLITS["holdout"]["end"]) if final_holdout else HOLDOUT_GUARD


def load_klines(market: str = "fut", end: pd.Timestamp | None = None, final_holdout: bool = False,
                raw: bool = False) -> pd.DataFrame:
    """1-minute bars indexed by bar OPEN time (UTC). A bar with open_time t covers [t, t+1min) and
    is only known at t+1min.  Unless raw=True the frame is re-indexed to a complete 1-minute grid;
    missing minutes are filled flat at the previous close with zero volume and filled=True."""
    end = end or default_end(final_holdout)
    _check_end(end, final_holdout)
    df = pd.concat([pd.read_parquet(f) for f in _months(f"klines_1m_{market}", end)], ignore_index=True)
    df = df[df["open_time"] < end]
    if raw:
        return df
    df = df.drop_duplicates("open_time").set_index("open_time").sort_index()
    full = pd.date_range(df.index[0], df.index[-1], freq="1min", tz="UTC")
    filled = ~full.isin(df.index)
    df = df.reindex(full)
    df["filled"] = filled
    c = df["close"].ffill()
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].where(~df["filled"], c)
    for col in ("volume", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume"):
        df[col] = df[col].fillna(0.0)
    df.index.name = "open_time"
    return df


def load_funding(end: pd.Timestamp | None = None, final_holdout: bool = False) -> pd.Series:
    """Realised funding rates indexed by funding timestamp (rounded to the minute)."""
    end = end or default_end(final_holdout)
    _check_end(end, final_holdout)
    df = pd.concat([pd.read_parquet(f) for f in _months("funding", end)], ignore_index=True)
    df["time"] = df["time"].dt.round("1min")
    s = df.drop_duplicates("time").set_index("time")["rate"].sort_index()
    return s[s.index < end]


def load_metrics(end: pd.Timestamp | None = None, final_holdout: bool = False) -> pd.DataFrame:
    """5-minute open interest etc. Index = snapshot time (data known at that time)."""
    end = end or default_end(final_holdout)
    _check_end(end, final_holdout)
    df = pd.concat([pd.read_parquet(f) for f in _months("metrics", end)], ignore_index=True)
    df["time"] = df["time"].dt.round("1min")
    df = df.drop_duplicates("time").set_index("time").sort_index()
    return df[df.index < end]


def resample(df1: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample 1m bars to `rule` bars labelled by OPEN time (left-closed, left-labelled).
    A resampled bar with label t is complete only at t + rule."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
           "quote_volume": "sum", "count": "sum", "taker_buy_volume": "sum", "filled": "mean"}
    out = df1.resample(rule, label="left", closed="left").agg(agg)
    return out.dropna(subset=["open"])
