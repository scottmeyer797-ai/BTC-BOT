#!/usr/bin/env python3
"""Download BTCUSDT data from the Binance public archive (data.binance.vision) into data/ as Parquet.

  python scripts/download_data.py                  # train + validation months only
  python scripts/download_data.py --final-holdout  # ALSO the holdout months (freeze step only!)

Resumable: existing parquet files are skipped. Every zip is verified against its .CHECKSUM (sha256).
No API key needed.
"""
from __future__ import annotations
import argparse, hashlib, io, sys, time, urllib.request, urllib.error, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from btcbot.config import DATA, SPLITS, FIRST_HOLDOUT_MONTH  # noqa: E402

BASE = "https://data.binance.vision/data"
SYM = SPLITS["symbol"]
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
         "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def fetch(url: str, tries: int = 5) -> bytes | None:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except Exception as e:  # network
            err = e
        time.sleep(2 ** i)
    raise RuntimeError(f"failed {url}: {err}")


def fetch_zip_csv(url: str) -> bytes | None:
    raw = fetch(url)
    if raw is None:
        return None
    chk = fetch(url + ".CHECKSUM")
    if chk is not None:
        want = chk.decode().split()[0]
        got = hashlib.sha256(raw).hexdigest()
        if want != got:
            raise RuntimeError(f"checksum mismatch {url}")
    z = zipfile.ZipFile(io.BytesIO(raw))
    return z.read(z.namelist()[0])


def read_csv_maybe_header(b: bytes, cols: list[str] | None) -> pd.DataFrame:
    first = b[:200].decode(errors="replace").split("\n")[0]
    has_header = not first.split(",")[0].strip().lstrip("-").replace(".", "").isdigit()
    if has_header:
        df = pd.read_csv(io.BytesIO(b))
    else:
        df = pd.read_csv(io.BytesIO(b), header=None, names=cols)
    return df


def klines(market: str, month: str) -> str:
    sub = "futures/um" if market == "fut" else "spot"
    out = DATA / f"klines_1m_{market}" / f"{month}.parquet"
    if out.exists():
        return "skip"
    b = fetch_zip_csv(f"{BASE}/{sub}/monthly/klines/{SYM}/1m/{SYM}-1m-{month}.zip")
    if b is None:
        return "MISSING"
    df = read_csv_maybe_header(b, KCOLS)
    df.columns = KCOLS[: len(df.columns)]
    t = df["open_time"].astype("int64")
    if t.iloc[0] > 10 ** 14:  # spot archive switched to microseconds in 2025
        t = t // 1000
    df["open_time"] = pd.to_datetime(t, unit="ms", utc=True)
    df = df.drop(columns=["close_time", "ignore"])
    for c in df.columns[1:]:
        df[c] = df[c].astype("float64")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return f"{len(df)}"


def funding(month: str) -> str:
    out = DATA / "funding" / f"{month}.parquet"
    if out.exists():
        return "skip"
    b = fetch_zip_csv(f"{BASE}/futures/um/monthly/fundingRate/{SYM}/{SYM}-fundingRate-{month}.zip")
    if b is None:
        return "MISSING"
    df = pd.read_csv(io.BytesIO(b))
    df = df.rename(columns={"calc_time": "time", "last_funding_rate": "rate"})
    df["time"] = pd.to_datetime(df["time"].astype("int64"), unit="ms", utc=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    df[["time", "rate"]].to_parquet(out, index=False)
    return f"{len(df)}"


def metrics_month(month: str) -> str:
    out = DATA / "metrics" / f"{month}.parquet"
    if out.exists():
        return "skip"
    days = pd.date_range(month + "-01", periods=pd.Period(month).days_in_month, freq="D")
    def one(d):
        b = fetch_zip_csv(f"{BASE}/futures/um/daily/metrics/{SYM}/{SYM}-metrics-{d:%Y-%m-%d}.zip")
        return None if b is None else pd.read_csv(io.BytesIO(b))
    with ThreadPoolExecutor(8) as ex:
        parts = list(ex.map(one, days))
    missing = sum(p is None for p in parts)
    parts = [p for p in parts if p is not None]
    if not parts:
        return "MISSING"
    df = pd.concat(parts, ignore_index=True)
    df["time"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.rename(columns={"sum_open_interest": "oi", "sum_open_interest_value": "oi_value"})
    keep = ["time", "oi", "oi_value"] + [c for c in df.columns if "ratio" in c]
    out.parent.mkdir(parents=True, exist_ok=True)
    df[keep].to_parquet(out, index=False)
    return f"{len(df)} rows, {missing} days missing"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-holdout", action="store_true",
                    help="ALSO download the final holdout months. Only at the freeze step.")
    a = ap.parse_args()
    last = pd.Period(SPLITS["holdout"]["end"], "M") - 1 if a.final_holdout else pd.Period(FIRST_HOLDOUT_MONTH, "M") - 1
    months = [str(p) for p in pd.period_range(SPLITS["data_start"][:7], last, freq="M")]
    for m in months:
        if m >= FIRST_HOLDOUT_MONTH and not a.final_holdout:
            raise SystemExit("refusing holdout month without --final-holdout")
    jobs = [("fut", m) for m in months] + [("spot", m) for m in months]
    with ThreadPoolExecutor(6) as ex:
        for (mk, m), r in zip(jobs, ex.map(lambda j: klines(*j), jobs)):
            if r != "skip":
                print("klines", mk, m, r, flush=True)
        for m, r in zip(months, ex.map(funding, months)):
            if r != "skip":
                print("funding", m, r, flush=True)
    for m in months:
        r = metrics_month(m)
        if r != "skip":
            print("metrics", m, r, flush=True)


if __name__ == "__main__":
    main()
