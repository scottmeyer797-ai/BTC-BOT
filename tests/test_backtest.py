"""Fill-model unit tests on synthetic bars."""
import numpy as np, pandas as pd, pytest
from btcbot.backtest import run_backtest
from btcbot.costs import Costs

IDX = pd.date_range("2021-01-01", periods=60, freq="1min", tz="UTC")
NOFUND = pd.Series([], index=pd.DatetimeIndex([], tz="UTC"), dtype=float)
ZERO = Costs(0, 0, 0, 0)


def bars(o, h, l):
    n = len(IDX)
    df = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}, index=IDX)
    for i, v in o.items(): df.iloc[i, 0] = v
    for i, v in h.items(): df.iloc[i, 1] = v
    for i, v in l.items(): df.iloc[i, 2] = v
    df["high"] = df[["open", "high"]].max(axis=1); df["low"] = df[["open", "low"]].min(axis=1)
    return df


def sig(i, d=1, stop=1.0, tgt=2.0, hold=10, **kw):
    return pd.DataFrame({"dir": [d], "stop_dist": [stop], "tgt_dist": [tgt], "max_hold": [hold], **{k: [v] for k, v in kw.items()}}, index=[IDX[i]])


def bt(df, s, costs=ZERO, fund=NOFUND, **kw):
    return run_backtest(df, fund, s, IDX[0], IDX[-1] + pd.Timedelta(minutes=1), costs, **kw)


def test_entry_at_bar_open_plus_slippage_and_fees():
    df = bars({5: 101.0, 15: 103.0}, {}, {})
    c = Costs(taker=0.001, maker=0.0, slip_mkt=0.01, slip_stop=0.0)
    t = bt(df, sig(5, hold=10, stop=50, tgt=50), c).iloc[0]
    assert t.entry_px == pytest.approx(101.0 * 1.01)          # open of entry bar, worse by slippage
    assert t.reason == "time" and t.exit_px == pytest.approx(103.0 * 0.99)
    assert t.net == pytest.approx(t.gross - 0.001 - 0.001 * t.exit_px / t.entry_px)


def test_stop_before_target_same_bar():
    df = bars({}, {6: 103.0}, {6: 98.0})
    t = bt(df, sig(5)).iloc[0]
    assert t.reason == "stop" and t.exit_px == pytest.approx(99.0) and t.R == pytest.approx(-1.0)


def test_target_touch_does_not_fill_trade_through_does():
    t = bt(bars({}, {6: 102.0}, {}), sig(5)).iloc[0]          # exactly touches 102 -> no fill
    assert t.reason == "time"
    t = bt(bars({}, {6: 102.1}, {}), sig(5)).iloc[0]          # trades one tick through -> fill at 102
    assert t.reason == "target" and t.exit_px == pytest.approx(102.0) and t.R == pytest.approx(2.0)


def test_gap_through_stop_fills_at_open_with_slippage():
    df = bars({7: 95.0}, {}, {})
    c = Costs(0, 0, 0, slip_stop=0.01)
    t = bt(df, sig(5), c).iloc[0]
    assert t.reason == "stop" and t.exit_px == pytest.approx(95.0 * 0.99) and t.R < -5


def test_short_mirror():
    t = bt(bars({}, {6: 101.5}, {6: 97.0}), sig(5, d=-1)).iloc[0]
    assert t.reason == "stop" and t.exit_px == pytest.approx(101.0)
    t = bt(bars({}, {}, {6: 97.9}), sig(5, d=-1)).iloc[0]
    assert t.reason == "target" and t.exit_px == pytest.approx(98.0)


def test_funding_charged_to_longs_credited_to_shorts():
    fund = pd.Series([0.001], index=[IDX[8]])
    tl = bt(bars({}, {}, {}), sig(5, hold=10), fund=fund).iloc[0]
    ts_ = bt(bars({}, {}, {}), sig(5, d=-1, hold=10), fund=fund).iloc[0]
    assert tl.net == pytest.approx(-0.001) and ts_.net == pytest.approx(0.001)
    out = bt(bars({}, {}, {}), sig(20, hold=10), fund=fund).iloc[0]   # print before entry: not charged
    assert out.net == pytest.approx(0.0)


def test_one_position_at_a_time():
    s = pd.concat([sig(5, hold=10), sig(8, hold=10), sig(30, hold=5)])
    assert len(bt(bars({}, {}, {}), s)) == 2


def test_limit_entry_needs_trade_through():
    s = sig(5, stop=1.0, tgt=2.0, hold=10, limit_off=0.5)
    assert len(bt(bars({}, {}, {6: 99.5}), s, mode=1)) == 0          # touch only
    t = bt(bars({}, {}, {6: 99.4}), s, mode=1).iloc[0]               # through
    assert t.entry_px == pytest.approx(99.5)
    t = bt(bars({}, {6: 105.0}, {6: 98.0}), s, mode=1).iloc[0]       # fill bar also hits stop -> stopped
    assert t.reason == "stop"


def test_cost_multiplier():
    c = Costs(taker=0.001, maker=0.0, slip_mkt=0.0, slip_stop=0.0)
    a = bt(bars({}, {}, {}), sig(5), c).iloc[0].net
    b = bt(bars({}, {}, {}), sig(5), c.scaled(1.5)).iloc[0].net
    assert b == pytest.approx(1.5 * a)
