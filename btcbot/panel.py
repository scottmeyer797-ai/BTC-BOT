"""Build the working panel: 1m bars + 5m features, cached to data/cache (git-ignored)."""
from __future__ import annotations
import pandas as pd
from . import data
from .features import build_features
from .config import DATA, split_bounds


def load_panel(final_holdout: bool = False, cache: bool = True):
    """Returns (df1m, f5m, funding). Data end is the validation end unless final_holdout=True."""
    import hashlib
    from . import features as _f
    h = hashlib.sha1(open(_f.__file__, "rb").read()).hexdigest()[:10]   # cache invalidates when features.py changes
    tag = "full" if final_holdout else "dev"
    p = DATA / "cache" / f"features_{tag}_{h}.parquet"
    df1 = data.load_klines("fut", final_holdout=final_holdout)
    fund = data.load_funding(final_holdout=final_holdout)
    if cache and p.exists():
        f = pd.read_parquet(p)
    else:
        oi = data.load_metrics(final_holdout=final_holdout)["oi"]
        spot = data.load_klines("spot", final_holdout=final_holdout)
        f = build_features(df1, oi, spot)
        p.parent.mkdir(parents=True, exist_ok=True)
        f.to_parquet(p)
    return df1, f, fund


def in_split(index: pd.DatetimeIndex, name: str):
    a, b = split_bounds(name)
    return (index >= a) & (index < b)
