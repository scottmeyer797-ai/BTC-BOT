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

VARIANTS.update({
    "V06": dict(event="h1_disp", k_stop=2.0, rr=2.0, max_hold=720),
    "V07": dict(event="cascade", event_kw=dict(z=4, v=5, oi_drop=0.010), k_stop=3.0, rr=1.0, max_hold=240),
    "V08": dict(event="trend_sweep", hours=(7, 17), k_stop=1.0, rr=2.0, max_hold=240),
    "V09": dict(event="h1_disp_oi", event_kw=dict(oi_sign=1), **_X),
    "V10": dict(event="h1_disp_oi", event_kw=dict(oi_sign=-1), **_X),
})

VARIANTS.update({
    "V11": dict(event="cascade_reclaim", event_kw=dict(z=3, v=3, oi_drop=0.005, window=12), k_stop=0.5, rr=2.0, max_hold=240),
    "V12": dict(event="cascade_reclaim", event_kw=dict(z=4, v=5, oi_drop=0.010, window=12), k_stop=0.5, rr=2.0, max_hold=240),
    "V13": dict(event="h1_disp_oi", event_kw=dict(oi_sign=1), k_stop=2.0, rr=2.0, max_hold=720),
    "V14": dict(event="h1_disp", k_stop=1.0, rr=2.0, max_hold=240, limit_off_atr=0.25, limit_win=60),
})

VARIANTS.update({
    "V15": dict(event="h1_disp_lead", event_kw=dict(lead="spot"), **_X),
    "V16": dict(event="h1_disp_lead", event_kw=dict(lead="perp"), **_X),
})

VARIANTS.update({
    "V17": dict(event="h1_disp_lead_k", event_kw=dict(lead="spot", k=1.5), **_X),
    "V18": dict(event="h1_disp_lead_k", event_kw=dict(lead="spot", k=2.0), **_X),
})

VARIANTS.update({
    "V19": dict(event="h1_disp", k_stop=3.0, rr=2.0, max_hold=1440),
    "V20": dict(event="h1_disp", k_stop=2.0, rr=3.0, max_hold=720),
})
