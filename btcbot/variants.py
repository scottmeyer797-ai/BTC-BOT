"""Registry of every strategy variant tried (max 25). Never delete entries; failed ones stay.
Each entry is pre-registered in research_log.md before it is run."""
VARIANTS: dict[str, dict] = {}

_X = dict(k_stop=1.0, rr=2.0, max_hold=240)
VARIANTS.update({
    "V01": dict(event="cascade", event_kw=dict(z=4, v=5, oi_drop=0.010), **_X),
    "V02": dict(event="cascade", event_kw=dict(z=5, v=5, oi_drop=0.015), **_X),
    "V03": dict(event="cascade", event_kw=dict(z=3, v=3, oi_drop=0.005), **_X),
    "V04": dict(event="h1_disp", **_X),
    "V05": dict(event="asia_sweep", flip=-1, **_X),
})
