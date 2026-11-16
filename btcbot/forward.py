"""Forward-test (paper) harness. NEVER places orders; needs no API keys; talks only to public
market-data endpoints.

Live:    python -m btcbot.forward --live --variant V06
Replay:  python -m btcbot.forward --replay 2023-01-10 2023-02-10 --variant V06
         (feeds historical 1m bars one at a time through the SAME engine and compares the resulting
          trades with the vectorised backtest)

The engine consumes CLOSED 1-minute bars. On every bar that completes a 5-minute bar it recomputes
the features on its rolling buffer with btcbot.features.build_features and calls
btcbot.strategy.make_signals - the same functions the backtest uses. Hypothetical fills follow the
rules of btcbot.backtest (next-bar-open entry + slippage, stop-first, trade-through targets, real
funding, taker/maker fees).

Logs: forward_logs/<variant>_signals.csv and forward_logs/<variant>_paper_trades.csv
Limit: kline-only variants (events that need open interest or spot need extra feeds).
"""
from __future__ import annotations
import argparse, asyncio, csv, json, time, urllib.request
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pandas as pd
from .features import build_features
from .strategy import make_signals
from .costs import Costs, BASE, TICK, MAX_LEVERAGE, RISK_PER_TRADE
from .config import ROOT

COLS = ["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume"]
LOG_DIR = ROOT / "forward_logs"
FAPI = "https://fapi.binance.com"
WS = "wss://fstream.binance.com/ws/btcusdt@kline_1m"


@dataclass
class Position:
    dir: int; fill_time: pd.Timestamp; entry_px: float; level: float; stop: float; tgt: float
    last_time: pd.Timestamp; risk: float; signal_time: pd.Timestamp; funding: float = 0.0


@dataclass
class PaperEngine:
    params: dict
    costs: Costs = BASE
    buffer_minutes: int = 30 * 1440
    funding_lookup: object = None          # callable(ts) -> rate or None
    buf: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLS, dtype=float))
    pos: Position | None = None
    pending: dict | None = None
    trades: list = field(default_factory=list)
    signals: list = field(default_factory=list)

    def warmup(self, df1: pd.DataFrame):
        self.buf = df1[COLS].iloc[-self.buffer_minutes:].copy()

    # ---- fills (mirror of backtest._simulate) -------------------------------------------------
    def _close(self, t, px, reason, fee_out):
        p = self.pos; c = self.costs
        gross = p.dir * (px - p.entry_px) / p.entry_px
        net = gross - c.taker * c.mult - fee_out * (px / p.entry_px) - p.funding
        lev = min(RISK_PER_TRADE / p.risk, MAX_LEVERAGE)
        tr = dict(signal_time=p.signal_time, entry_time=p.fill_time, exit_time=t, dir=p.dir, entry_px=p.entry_px,
                  exit_px=px, reason=reason, gross=gross, net=net, risk=p.risk, R=net / p.risk, eq_ret=lev * net)
        self.trades.append(tr); self.pos = None
        return tr

    def on_bar(self, t: pd.Timestamp, bar: dict) -> dict | None:
        """t = OPEN time of a 1m bar that has just CLOSED. Returns a closed trade dict or None."""
        c = self.costs; m = c.mult; out = None
        if len(self.buf) and t <= self.buf.index[-1]:
            return None                                    # duplicate / out-of-order bar
        self.buf.loc[t] = [float(bar[k]) for k in COLS]
        if len(self.buf) > self.buffer_minutes + 1440:
            self.buf = self.buf.iloc[-self.buffer_minutes:]
        o, h, l = float(bar["open"]), float(bar["high"]), float(bar["low"])
        if self.pending is not None and self.pos is None:  # market entry at THIS bar's open
            s = self.pending; d = s["dir"]
            self.pos = Position(d, t, o * (1 + d * c.slip_mkt * m), o, o - d * s["stop_dist"], o + d * s["tgt_dist"],
                                t + pd.Timedelta(minutes=int(s["max_hold"])), s["stop_dist"] / o, s["signal_time"])
        self.pending = None
        if self.pos is not None:
            p = self.pos; d = p.dir
            if self.funding_lookup is not None:
                r = self.funding_lookup(t)
                if r:
                    p.funding += d * r
            if t >= p.last_time:                           # time stop: exit at this bar's open
                out = self._close(t, o * (1 - d * c.slip_mkt * m), "time", c.taker * m)
            elif d > 0 and l <= p.stop:
                out = self._close(t, min(p.stop, o) * (1 - c.slip_stop * m), "stop", c.taker * m)
            elif d > 0 and h >= p.tgt + TICK:
                out = self._close(t, p.tgt, "target", c.maker * m)
            elif d < 0 and h >= p.stop:
                out = self._close(t, max(p.stop, o) * (1 + c.slip_stop * m), "stop", c.taker * m)
            elif d < 0 and l <= p.tgt - TICK:
                out = self._close(t, p.tgt, "target", c.maker * m)
        if t.minute % 5 == 4:                              # a 5m bar has just completed
            self._on_5m_close(t + pd.Timedelta(minutes=1))
        return out

    def _on_5m_close(self, t_close: pd.Timestamp):
        df1 = self.buf.copy()
        df1["filled"] = False
        f = build_features(df1)
        sig = make_signals(f, self.params)
        if len(sig) == 0 or sig.index[-1] != t_close:
            return
        s = sig.iloc[-1]
        if s["dir"] != 0 and np.isfinite(s["stop_dist"]) and s["stop_dist"] > 0:
            rec = dict(signal_time=t_close, dir=int(s["dir"]), stop_dist=float(s["stop_dist"]),
                       tgt_dist=float(s["tgt_dist"]), max_hold=int(s["max_hold"]), taken=self.pos is None)
            self.signals.append(rec)
            if self.pos is None:
                self.pending = rec


# ---- replay ------------------------------------------------------------------------------------
def replay(variant: str, start: str, end: str, warm_days: int = 6, mult: float = 1.0):
    from .panel import load_panel
    from .variants import VARIANTS
    from .backtest import run_backtest
    df1, f, fund = load_panel()
    a, b = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    p = VARIANTS[variant]
    fd = fund.to_dict()
    eng = PaperEngine(p, BASE.scaled(mult), buffer_minutes=warm_days * 1440, funding_lookup=lambda t: fd.get(t))
    eng.warmup(df1[(df1.index >= a - pd.Timedelta(days=warm_days)) & (df1.index < a)])
    win = df1[(df1.index >= a) & (df1.index < b)]
    recs = win[COLS].to_dict("records")
    for t, bar in zip(win.index, recs):
        eng.on_bar(t, bar)
    fwd = pd.DataFrame(eng.trades)
    bt = run_backtest(df1, fund, make_signals(f, p), a + pd.Timedelta(minutes=5), b, BASE.scaled(mult))
    # compare only trades that closed inside the window (the backtest force-closes at `end`)
    bt = bt[bt["reason"] != "end"].reset_index(drop=True)
    if len(fwd):
        fwd = fwd[fwd["exit_time"].isin(bt["exit_time"]) | (fwd["exit_time"] < b - pd.Timedelta(days=2))].reset_index(drop=True)
    return fwd, bt, pd.DataFrame(eng.signals)


def compare(fwd: pd.DataFrame, bt: pd.DataFrame) -> dict:
    n = min(len(fwd), len(bt))
    ok = len(fwd) == len(bt)
    maxdiff = 0.0
    if n:
        for c in ("entry_px", "exit_px", "net", "R"):
            maxdiff = max(maxdiff, float(np.abs(fwd[c].to_numpy()[:n] - bt[c].to_numpy()[:n]).max()))
        ok &= bool((fwd["entry_time"].to_numpy()[:n] == bt["entry_time"].to_numpy()[:n]).all())
        ok &= bool((fwd["exit_time"].to_numpy()[:n] == bt["exit_time"].to_numpy()[:n]).all())
        ok &= bool((fwd["reason"].to_numpy()[:n] == bt["reason"].to_numpy()[:n]).all())
    return dict(forward_trades=len(fwd), backtest_trades=len(bt), identical=bool(ok and maxdiff < 1e-9), max_abs_diff=maxdiff)


# ---- live --------------------------------------------------------------------------------------
def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def _rest_klines(minutes: int) -> pd.DataFrame:
    rows = []; end = int(time.time() * 1000)
    while len(rows) < minutes:
        k = _get(f"{FAPI}/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=1500&endTime={end}")
        if not k:
            break
        rows = k + rows; end = k[0][0] - 1
    df = pd.DataFrame(rows).iloc[:, [0, 1, 2, 3, 4, 5, 7, 8, 9, 10]]
    df.columns = ["open_time"] + COLS
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.drop_duplicates("open_time").set_index("open_time").astype(float).sort_index()
    return df[df.index < pd.Timestamp.now(tz="UTC").floor("1min")]      # closed bars only


def _append(path: Path, rec: dict):
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rec))
        if new:
            w.writeheader()
        w.writerow(rec)


async def live(variant: str):
    import websockets
    from .variants import VARIANTS
    LOG_DIR.mkdir(exist_ok=True)
    fcache: dict = {}

    def funding_lookup(t):
        if t.minute or t.hour % 8:
            return None
        if t not in fcache:
            try:
                for x in _get(f"{FAPI}/fapi/v1/fundingRate?symbol=BTCUSDT&limit=5"):
                    fcache[pd.Timestamp(x["fundingTime"], unit="ms", tz="UTC").round("1min")] = float(x["fundingRate"])
            except Exception as e:  # noqa
                print("funding fetch failed", e)
        return fcache.get(t)

    eng = PaperEngine(VARIANTS[variant], BASE, funding_lookup=funding_lookup)
    eng.warmup(_rest_klines(30 * 1440))
    print(f"[paper] warm-up bars: {len(eng.buf)}; last {eng.buf.index[-1]}. PAPER ONLY - no orders are ever sent.")
    n_sig = 0
    while True:
        try:
            async with websockets.connect(WS, ping_interval=120) as ws:
                async for raw in ws:
                    k = json.loads(raw)["k"]
                    if not k["x"]:
                        continue
                    t = pd.Timestamp(k["t"], unit="ms", tz="UTC")
                    if t > eng.buf.index[-1] + pd.Timedelta(minutes=1):      # gap after reconnect: back-fill
                        miss = _rest_klines(int((t - eng.buf.index[-1]).total_seconds() // 60) + 5)
                        for tt, row in miss[(miss.index > eng.buf.index[-1]) & (miss.index < t)].iterrows():
                            eng.on_bar(tt, row.to_dict())
                    bar = dict(open=k["o"], high=k["h"], low=k["l"], close=k["c"], volume=k["v"], quote_volume=k["q"],
                               count=k["n"], taker_buy_volume=k["V"], taker_buy_quote_volume=k["Q"])
                    tr = eng.on_bar(t, bar)
                    if tr:
                        _append(LOG_DIR / f"{variant}_paper_trades.csv", tr); print("[paper] trade closed", tr)
                    for s in eng.signals[n_sig:]:
                        _append(LOG_DIR / f"{variant}_signals.csv", s); print("[paper] signal", s)
                    n_sig = len(eng.signals)
        except Exception as e:  # reconnect
            print("[paper] stream error, reconnecting in 5s:", repr(e)); await asyncio.sleep(5)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="V06")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--replay", nargs=2, metavar=("START", "END"))
    a = ap.parse_args()
    if a.replay:
        fwd, bt, sig = replay(a.variant, *a.replay)
        print(compare(fwd, bt)); print(fwd.tail(10).to_string())
    elif a.live:
        asyncio.run(live(a.variant))
