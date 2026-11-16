#!/usr/bin/env python3
"""Longer replay equivalence check of the forward harness -> reports/forward_replay.json (slow: ~15 min)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from btcbot.forward import replay, compare
from btcbot.config import REPORTS
out = {}
for vid, a, b in [("V06", "2023-01-10", "2023-02-20"), ("V04", "2021-05-01", "2021-05-25")]:
    fwd, bt, sig = replay(vid, a, b)
    out[f"{vid} {a}..{b}"] = dict(compare(fwd, bt), signals=len(sig))
    print(out, flush=True)
(REPORTS / "forward_replay.json").write_text(json.dumps(out, indent=2))
