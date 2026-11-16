"""Look-ahead / leakage tests. Require downloaded data (train period only is touched)."""
import numpy as np, pandas as pd, pytest
from btcbot import data
from btcbot.config import HOLDOUT_GUARD, DATA, split_bounds
from btcbot.features import build_features
from btcbot.strategy import make_signals, EVENT_FUNCS
from btcbot.evaluate import bounds

pytestmark = pytest.mark.skipif(not (DATA / "klines_1m_fut").exists(), reason="data not downloaded")


@pytest.fixture(scope="module")
def chunk():
    df1 = data.load_klines("fut", end=pd.Timestamp("2021-07-01", tz="UTC"))
    df1 = df1[df1.index >= pd.Timestamp("2021-04-20", tz="UTC")]
    oi = data.load_metrics(end=pd.Timestamp("2021-07-01", tz="UTC"))["oi"]
    return df1, oi


def test_holdout_guard_refuses():
    with pytest.raises(data.HoldoutAccessError):
        data.load_klines("fut", end=HOLDOUT_GUARD + pd.Timedelta(days=1))
    with pytest.raises(data.HoldoutAccessError):
        data.load_funding(end=split_bounds("holdout")[1])
    with pytest.raises(data.HoldoutAccessError):
        bounds("holdout")
    assert data.load_klines("fut").index[-1] < HOLDOUT_GUARD


def test_features_are_causal_by_truncation(chunk):
    """Features at row t computed on data truncated at t+5m must equal the full-sample features."""
    df1, oi = chunk
    full = build_features(df1, oi)
    rng = np.random.default_rng(0)
    cuts = rng.choice(np.arange(len(full) - 4000, len(full) - 1), size=12, replace=False)
    for c in cuts:
        t_close = full.index[c] + pd.Timedelta(minutes=5)
        part = build_features(df1[df1.index < t_close], oi[oi.index <= t_close])
        a, b = full.iloc[c], part.iloc[-1]
        assert part.index[-1] == full.index[c]
        for col in full.columns:
            x, y = a[col], b[col]
            assert (pd.isna(x) and pd.isna(y)) or np.isclose(float(x), float(y), rtol=1e-9, atol=1e-9), (col, full.index[c], x, y)


def test_signals_unchanged_when_future_is_scrambled(chunk):
    """Replace all prices after a cut with garbage: signals up to the cut must be identical."""
    df1, oi = chunk
    cut = df1.index[len(df1) - 20000]
    mod = df1.copy()
    fut = mod.index >= cut
    rng = np.random.default_rng(1)
    for c in ("open", "high", "low", "close"):
        mod.loc[fut, c] = mod.loc[fut, c] * (1 + rng.normal(0, 0.05, fut.sum()))
    mod.loc[fut, "high"] = mod.loc[fut, ["open", "high", "low", "close"]].max(axis=1)
    mod.loc[fut, "low"] = mod.loc[fut, ["open", "high", "low", "close"]].min(axis=1)
    mod.loc[fut, "volume"] *= 3; mod.loc[fut, "taker_buy_volume"] *= 2
    oi2 = oi.copy(); oi2[oi2.index > cut] *= 0.5
    fa, fb = build_features(df1, oi), build_features(mod, oi2)
    for ev in EVENT_FUNCS:
        p = dict(event=ev, k_stop=1.0, rr=2.0, max_hold=240)
        sa, sb = make_signals(fa, p), make_signals(fb, p)
        keep = sa.index <= cut            # entry time <= cut  => signal bar closed at or before the cut
        pd.testing.assert_frame_equal(sa[keep], sb[keep])
        assert (sa[keep]["dir"] != 0).sum() > 0 or ev in ("h1_disp",)


def test_entry_is_strictly_after_signal_bar(chunk):
    df1, oi = chunk
    f = build_features(df1, oi)
    s = make_signals(f, dict(event="cascade", k_stop=1.0, rr=2.0, max_hold=240))
    assert (s.index == f.index + pd.Timedelta(minutes=5)).all()   # entry stamp = close of the signal bar
    # the entry bar is not part of the signal bar: its open comes after the last 1m bar used
    i = np.where(s["dir"] != 0)[0][0]
    last_used = f.index[i] + pd.Timedelta(minutes=4)
    assert s.index[i] > last_used
