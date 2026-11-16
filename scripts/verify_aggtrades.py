#!/usr/bin/env python3
"""Check that the 1m kline taker-buy volume equals buy-aggressor volume aggregated from aggTrades,
on sample days (train period). If it matches, klines already carry exact 1m buy/sell aggression
(delta), so the ~60 GB aggTrades archive is not needed for 1m-resolution delta."""
import sys, io, zipfile, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd, numpy as np
from btcbot import data
k = data.load_klines("fut")
for day in ["2021-05-19", "2022-11-09", "2023-06-15"]:
    url = f"https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{day}.zip"
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=300).read()))
    raw = z.read(z.namelist()[0])
    hdr = raw[:20].decode().startswith("agg")
    cols = ["id", "price", "qty", "first", "last", "time", "is_buyer_maker"]
    t = pd.read_csv(io.BytesIO(raw), header=0 if hdr else None, names=cols)
    t["min"] = pd.to_datetime(t["time"], unit="ms", utc=True).dt.floor("1min")
    ibm = t["is_buyer_maker"].astype(str).str.lower().eq("true")
    g = pd.DataFrame({"vol": t.groupby("min")["qty"].sum(), "buy": t["qty"].where(~ibm, 0).groupby(t["min"]).sum()})
    kk = k.loc[g.index]
    print(day, "trades", len(t), "max|vol diff|", float((g["vol"] - kk["volume"]).abs().max()),
          "max|takerbuy diff|", float((g["buy"] - kk["taker_buy_volume"]).abs().max()),
          "total vol", round(float(g["vol"].sum())))
