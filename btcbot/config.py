"""Fixed split configuration and paths. The split is defined in config/splits.json and
was committed before any backtest."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
SPLITS = json.loads((ROOT / "config" / "splits.json").read_text())
SEED = SPLITS["seed"]


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def split_bounds(name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    d = SPLITS[name]
    return ts(d["start"]), ts(d["end"])


HOLDOUT_GUARD = ts(SPLITS["validation"]["end"])  # nothing at/after this may be loaded without the flag
FIRST_HOLDOUT_MONTH = SPLITS["first_holdout_month"]

# Sessions (UTC hours, half-open). BTC trades 24/7 so these are definitions, not exchange hours.
SESSIONS = {"asia": (0, 7), "london": (7, 13), "newyork": (13, 21), "late": (21, 24)}


def session_of_hour(h: int) -> str:
    for k, (a, b) in SESSIONS.items():
        if a <= h < b:
            return k
    raise ValueError(h)
