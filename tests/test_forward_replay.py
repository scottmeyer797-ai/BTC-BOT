"""The forward (paper) engine fed bar-by-bar must reproduce the vectorised backtest exactly."""
import pytest
from btcbot.config import DATA
pytestmark = pytest.mark.skipif(not (DATA / "klines_1m_fut").exists(), reason="data not downloaded")


def test_replay_matches_backtest():
    from btcbot.forward import replay, compare
    fwd, bt, sig = replay("V06", "2022-06-05", "2022-06-08")
    r = compare(fwd, bt)
    assert r["backtest_trades"] >= 2 and r["identical"], r
