# Research log — BTC liquidity-footprint strategy

All times UTC. Every hypothesis is written here and committed BEFORE its test is run.
Multiple-testing counters are kept at the bottom of this file and updated with every test.

## 2026-11-16 — Setup

- Branch `research/btc-strategy`.
- **Split fixed before any data was downloaded or any backtest run** (`config/splits.json`):
  - Train `[2020-01-01, 2024-02-01)` — 1492 days (59.8%)
  - Validation `[2024-02-08, 2025-06-01)` — 479 days after 7-day embargo
  - Final holdout `[2025-06-08, 2026-11-01)` — 511 days after 7-day embargo (20.5% incl. embargo)
  - Boundaries are month-aligned so the downloader can refuse whole holdout months (>= 2025-06)
    unless `--final-holdout` is passed. The loader refuses the same dates.
- **Pass criteria (fixed now, from the brief; not to be moved):** on OOS data (Validation and Holdout), at 1.0x and 1.5x costs:
  net expectancy > +0.15R/trade with 90% bootstrap CI lower bound > 0; >= 150 OOS trades (else INCONCLUSIVE);
  beats random-entry baseline and buy-and-hold; profit factor > 1.2; max drawdown acceptable at 1% risk
  (I fix "acceptable" = max DD <= 20% of equity); profitable in >= 70% of calendar quarters and across regimes.
- Variant budget: max 25 strategy variants. Event definitions tried in Phase 0 are counted separately and both are reported.
- Environment facts: `data.binance.vision` reachable. `fapi.binance.com` is blocked by the sandbox proxy (403) —
  REST/websocket live data cannot be reached from this container.
- Liquidation data: the archive prefix `data/futures/um/daily/liquidationSnapshot/BTCUSDT/` is empty (S3 listing returns no keys).
  => no liquidation feed is available; "liquidation cascade" must be a proxy built from price/volume/open-interest.

## 2026-11-16 — Data

- Downloaded train+validation months only (2020-01 .. 2025-05): futures 1m klines, spot 1m klines, funding, 5m metrics (open interest).
  Holdout months (>= 2025-06) are NOT on disk. See `reports/data_quality.md`.
- Futures 1m klines: 2,848,320 minutes, 0 missing, 0 duplicates, 351 zero-volume minutes (exchange outages/maintenance; excluded from signals).
- Spot: 2,325 missing minutes in 15 outage runs (spot is reference only; not used for signals).
- Funding: 5,934 prints, every 8h without gaps. Open interest: available only from 2020-09-01; 0.13% of 5m snapshots missing.
- aggTrades: `scripts/verify_aggtrades.py` shows 1m kline `taker_buy_volume` reproduces aggTrades buy-aggressor volume
  (delta correlation 0.99999 on 3 sample days; differences are millisecond minute-boundary attribution only). The full aggTrades archive is
  ~0.5-1.3 GB per month (~60 GB) and exceeds what is sensible here, so **1m delta comes from klines**. Limit: no
  trade-size information (cannot separate large prints from small) and no sub-minute sequencing.

## 2026-11-16 — Cost model (fixed before any test; `btcbot/costs.py`)

Taker 5 bps/side, maker 2 bps/side, market slippage 1 bp/side, stop slippage 2 bps + gap-through, real funding.
Round trip market-in/market-out = 12 bps (18 bps at 1.5x). Typical 5m ATR of BTC is 10-25 bps, so any
scalp with a stop of ~1 ATR pays 0.5-1R in costs: tight-stop scalping is arithmetically dead before any signal is considered.
Stops must be several ATR(5m) wide, or the gross edge per trade must exceed ~12 bps.

## 2026-11-16 — Phase 0 pre-registration (written BEFORE running the event study)

Event definitions (exact code in `btcbot/events.py`), hypothesised direction in brackets. 5m bars, event known at bar close,
entry at next bar open:

| id | event | hypothesis |
|---|---|---|
| E1 | sweep of previous UTC-day high/low, close back inside | fade: stops above/below the obvious level were harvested, move reverses |
| E2 | sweep of Asia-session (00-07 UTC) range during 07-21 UTC, close back inside | fade (same logic, session liquidity) |
| E3 | raid of equal highs/lows (>=2 pivots within 0.25 ATR, 8h window), close back | fade |
| E4 | displacement bar: range > 2.5 ATR, close in outer quartile, breaks 4h structure | follow: large urgent flow continues |
| E5 | cascade proxy: |5m ret| > 3 sigma, volume > 3x median, aggressive flow with the move | fade: forced flow exhausts, price bounces |
| E5b | E5 + open interest falls >= 0.5% during the bar (positions closed = liquidations) | fade |
| E6 | delta divergence: new 4h high on an up bar with net selling aggression (mirror at lows) | fade: absorption by passive seller |
| E7a | NY cash open drive (09:30-10:00 ET move > 1 sigma) | follow |
| E7b | London open drive (08:00-08:30 London move > 1 sigma) | follow |

9 definitions x 4 horizons (5/15/30/60 min) = **36 tests**.
Metric: signed forward return from next-bar open, minus the mean signed forward return of ALL bars in the same
(year, UTC hour, within-year realised-vol tercile) cell (= exact expectation of a matched random draw). CI by
day-clustered bootstrap. Net = gross - 12 bps.
**Decision rule fixed now:** an event qualifies as a strategy component only if the excess return has |t| >= 3.3
(Bonferroni for 36 two-sided tests at 5%) at >= 1 horizon AND the sign of the excess is the same in >= 3 of the 4 train years.
Events with 2 <= |t| < 3.3 are "weak": they may be used only as secondary filters. An event whose effect is significant with the
OPPOSITE sign to the hypothesis is reported as such and may be used in the observed direction (this is a data-driven
choice and is counted as an extra test in the multiple-testing total).

## 2026-11-16 — Phase 0 RESULT (train only; `reports/event_study.md`)

**No event meets the pre-registered bar (|t| >= 3.3). No event has positive net return at any horizon; the upper 97.5%
bound of net return is negative for every event/horizon except one noisy cell (E7b 60m, n=218).**

| event | n | best horizon | gross bps | excess bps [95% CI] | t | verdict |
|---|---|---|---|---|---|---|
| E1 PD sweep fade | 4657 | 15m | +0.5 | +0.5 [-1.0,+1.9] | 0.6 | no edge |
| E2 Asia sweep fade | 6154 | 60m | -3.0 | -3.1 [-6.3,-0.1] | -1.9 | no edge as fade; faint continuation |
| E3 equal H/L raid fade | 902 | 15m | +1.2 | +1.2 [-1.3,+3.7] | 1.0 | no edge |
| E4 displacement follow | 2720 | 5m | -2.6 | -2.7 [-4.6,-0.7] | -2.7 | WRONG SIGN: displacement bars mean-revert a little in the next 5m (weak) |
| E5 cascade fade | 6232 | 60m | +1.6 | +1.9 [-1.5,+5.1] | 1.1 | no edge |
| E5b cascade + OI drop fade | 2142 | 30m | +5.0 | +5.3 [+0.7,+10.1] | 2.2 | weak; right sign in all years; < costs |
| E6 delta divergence fade | 762 | 30m | +3.0 | +3.4 [-0.3,+7.3] | 1.8 | no edge (suggestive) |
| E7a NY open drive follow | 407 | 15m | -5.3 | -5.4 [-10.8,-0.6] | -2.1 | WRONG SIGN, weak (open drive fades) |
| E7b London open drive follow | 218 | 30m | -5.2 | -5.4 [-21,+6.6] | -0.8 | no edge |

Reading: the popular "liquidity sweep" patterns (E1, E2, E3) are statistically indistinguishable from random bars matched on
time of day and volatility. The only effect in the hypothesised direction with year-by-year consistency is the cascade with an
open-interest drop (forced position closing), ~5 bps over 30-60 min — less than half of the 12 bps round-trip cost.
Tests so far: 36.

### Phase 0b pre-registration (written BEFORE running)

Reason: costs are 12 bps, so only larger/longer effects can matter. Two legitimate follow-ups, both with market logic:
(1) dose-response — if E5b is truly forced-liquidation exhaustion, more extreme cascades (bigger move, volume, OI drop) should
bounce more; (2) longer horizons (30/60/120/240 min) and higher-timeframe versions.

| id | definition | hypothesis |
|---|---|---|
| E5c | cascade z>4, vol>5x, OI drop >= 1.0% | fade, larger effect than E5b |
| E5d | cascade z>5, vol>5x, OI drop >= 1.5% | fade, larger still |
| E5e | E5b but OI change strictly lagged one snapshot (robustness to OI timestamp latency) | fade; if the effect vanishes, E5b depended on zero-latency OI |
| E5b-long | E5b at the long horizons | fade |
| E1t | E1 only when the fade direction agrees with the 1H trend (close vs EMA50) | fade with HTF bias |
| E2r | E2 reversed (follow the Asia-range sweep) — data-driven sign flip | follow |
| E4h | 1H displacement bar (range > 2.5 ATR1h, outer-quartile close, breaks 24h high/low) | follow |

7 definitions x 4 horizons = 28 tests -> cumulative 64 tests; Bonferroni threshold becomes |t| >= 3.4. Same decision rule.

## 2026-11-16 — Phase 0b RESULT (train only; `reports/event_study_0b.md`)

| event | n | gross bps @30/60/120/240m | best excess [95% CI] | t | net @240m |
|---|---|---|---|---|---|
| E5b cascade+OI>=0.5% | 2142 | +5.0 / +4.1 / +7.5 / +8.9 | +7.5 [+1.1,+13.7] @120 | 2.3 | -3.1 |
| E5c z4,v5,OI>=1.0% | 779 | +5.0 / +4.8 / +9.6 / +16.8 | +16.1 [+2.0,+29.9] @240 | 2.3 | +4.8 |
| E5d z5,v5,OI>=1.5% | 388 | +9.5 / +8.0 / +17.8 / +24.3 | +23.2 [+1.5,+47.4] @240 | 2.0 | +12.3 |
| E5e lagged-OI cascade | 532 | +6.7 / +5.0 / +1.2 / +8.0 | n.s. | 1.1 | -4.0 |
| E1t PD sweep with 1H bias | 301 | +7.5 / -1.6 / 0.0 / 0.0 | n.s. | 1.6 | -12.0 |
| E2r Asia sweep FOLLOW | 6154 | +1.4 / +3.0 / +3.4 / +5.7 | +3.1 [0.0,+6.4] @60 | 1.9 | -6.3 |
| E4h 1H displacement follow | 405 | +3.0 / +4.4 / +9.4 / +19.6 | +18.4 [+1.2,+35.1] @240 | 2.1 | +7.6 |

- **Nothing reaches |t| >= 3.4. Formally, zero events qualify as strategy components.** Cumulative tests: 64. With 64 tests,
  ~3 results at |t|>2 are expected by chance alone; I observe about 8 cells above 2, clustered in two families.
- There IS a monotone dose-response in the cascade family (bigger flush + bigger OI drop -> bigger 4h bounce: 8.9 -> 16.8 -> 24.3 bps),
  which is what the forced-liquidation hypothesis predicts, and the sign is right in every train year for E5d@240. That is weak,
  suggestive evidence - not a credible edge. 2021 carries most of it.
- E5e: the effect needs the OI drop measured in the cascade bar itself; an OI drop one bar earlier carries nothing.
  The strategy therefore depends on reading open interest at the bar close (live: REST poll, feasible, but the archive
  timestamp alignment is an assumption — see Known weaknesses).
- The classic sweep patterns with HTF bias (E1t) do not help.

**PHASE 0 PROGRESS NOTE:** no event has a statistically credible edge after costs. Honest reading: the brief says only credible
events may become components, so the strict conclusion is already "no edge found". I nevertheless carry the two families whose
*net point estimate* is positive at 4h (cascade fade, 1H displacement follow) plus the frequent-but-weak ones into the strategy loop as an
EXPLORATORY test under the full protocol — explicitly a deviation from the strict rule, made because a stop/target structure
can in principle extract a different payoff than a fixed-horizon return. Any result is to be haircut for 64 event tests + all variants.

## 2026-11-16 — Strategy loop

Common structure (fixed stop, fixed RR, time stop; multi-timeframe): event on 5m bars, stop = k x ATR(1H,14), target = rr x stop,
time stop, market entry at next 1m open, one position at a time, 1% risk, leverage cap 5x.
Stops are scaled to 1H ATR (typ. 60-120 bps) so that the 12 bps round trip is ~0.1-0.2R rather than ~1R.

### Pre-registration V01-V05 (written BEFORE running; Train only)

| id | rule | prediction |
|---|---|---|
| V01 | cascade E5c (z>4, vol>5x, OI drop>=1%) fade; stop 1.0 ATR1h, RR 2, time stop 240m | exp > 0 but < +0.15R; fails bar |
| V02 | cascade E5d (z>5, vol>5x, OI>=1.5%) fade; same exits | exp higher than V01 (dose-response) but too few trades (<40/yr) |
| V03 | cascade E5b (z>3, vol>3x, OI>=0.5%) fade; same exits | exp <= 0 after costs |
| V04 | 1H displacement follow; stop 1.0 ATR1h, RR 2, time stop 240m | exp slightly > 0; inconsistent by year |
| V05 | Asia-range sweep FOLLOW (E2r); same exits | exp ~ 0 or negative after costs |

### Result V01-V05 (Train, 1.0x / 1.5x costs) — `reports/variants.csv`

| id | n | exp R 1.0x [90% CI] | exp R 1.5x | PF | random-entry mean R (p) | note |
|---|---|---|---|---|---|---|
| V01 | 762 | -0.246 [-0.32,-0.17] | -0.335 | 0.66 | -0.168 (p=0.97) | worse than random; gross R is already -0.10 |
| V02 | 386 | -0.276 [-0.38,-0.17] | -0.363 | 0.63 | -0.174 (0.97) | more extreme = no better |
| V03 | 1955 | -0.195 [-0.24,-0.15] | -0.283 | 0.71 | -0.170 (0.82) | fails |
| V04 | 405 | +0.058 [-0.05,+0.17] | -0.022 | 1.11 | -0.169 (0.003) | beats random; gross +0.19R; costs 0.13R; by year -0.13/+0.02/+0.35/-0.06 |
| V05 | 2353 | -0.145 [-0.19,-0.11] | -0.240 | 0.76 | -0.182 (0.08) | fails |

Diagnosis:
- Cascade fade: the positive 4h drift from Phase 0b does NOT survive a 1-ATR stop. 58% of trades are stopped; post-cascade
  volatility is far above the lagging 1H ATR and the flush typically continues before it bounces. My prediction "exp > 0" for V01 was wrong.
- Costs are ~0.13-0.15R per trade with a 1 ATR(1H) stop (~90 bps). Random entries lose exactly that.
- V04 is the only variant with a gross edge, but it is small, regime-dependent (2022 carries it) and gone at 1.5x costs.

### Pre-registration V06-V10 (written BEFORE running; Train only). Variants used so far: 5.

| id | rule | reasoning | prediction |
|---|---|---|---|
| V06 | 1H displacement follow; stop 2.0 ATR1h, RR 2, time stop 720m | cost diagnosis: halve cost-in-R and give continuation time | exp ~ +0.05..0.12R, still below bar, still regime-dependent |
| V07 | cascade E5c fade; stop 3.0 ATR1h, RR 1, time stop 240m | tests if the Phase-0b drift is extractable at all once the stop is out of the way | exp ~ 0..+0.03R (drift 17bps - 12bps over ~270bps risk); fails bar |
| V08 | "trend sweep": 1H trend up + 5m sweep of prior 4h low with close back above (mirror), London/NY 07-17 UTC; stop 1 ATR1h, RR 2, 240m | the user's preferred HTF-bias + LTF-liquidity-raid + session window style | Phase 0 (E1t) says no edge: exp ~ -0.15R (= costs) |
| V09 | 1H displacement WITH rising open interest over the hour; exits as V04 | rising OI = new positions = initiative flow that should continue | V09 > V04 |
| V10 | 1H displacement WITH falling open interest; exits as V04 | falling OI = squeeze/liquidations, fuel is spent | V10 < V04 |

### Result V06-V10 (Train). Variants used: 10.

| id | n | exp R 1.0x [90% CI] | exp R 1.5x | PF | by year 2020/21/22/23 | note |
|---|---|---|---|---|---|---|
| V06 | 384 | +0.081 [-0.01,+0.18] | +0.040 | 1.18 | +0.05/+0.13/+0.13/-0.07 | cost-in-R halves as predicted; still below bar |
| V07 | 688 | -0.073 [-0.11,-0.03] | -0.103 | 0.76 | — | even with the stop out of the way the cascade fade loses: drift is not extractable |
| V08 | 2026 | -0.207 [-0.25,-0.17] | -0.302 | 0.66 | — | HTF-bias + liquidity-raid + session window = random entries minus costs (random: -0.19R) |
| V09 | 155 | +0.126 [-0.05,+0.30] | +0.044 | 1.23 | -0.39/+0.11/+0.46/-0.10 | ordering V09 > V04 > V10 as predicted, differences not significant; 45 trades/yr = too few |
| V10 | 192 | +0.038 [-0.11,+0.19] | -0.042 | 1.07 | -0.16/-0.04/+0.25/-0.04 | |

Bug note: the simulator's array cache was keyed by `id(df)`; a unit test exposed that a recycled id could serve stale arrays.
Fixed (identity check with held reference). Real runs always used one long-lived frame; V04/V06 re-run gave identical numbers, so no result changed.

Diagnosis: the cascade family is dead (V01-V03, V07). The sweep family is dead (V05, V08). The only gross edge is
continuation after a 1H displacement that breaks 24h structure (gross +0.15..0.26R, net +0.06..0.13R), weak and 2022-heavy.

### Pre-registration V11-V14 (written BEFORE running; Train only)

| id | rule | reasoning | prediction |
|---|---|---|---|
| V11 | cascade E5b, then wait <= 60 min for a 5m reclaim bar (closes up and above prior bar high; mirrored); stop at flush extreme (floor 0.5 ATR1h), RR 2, 240m | V01 failed because it entered while the flush was still running; wait for the lower-timeframe turn and use the structural stop | most honest guess: -0.1R; would need > +0.15R |
| V12 | same with E5c cascade | dose | better than V11 if hypothesis true |
| V13 | 1H displacement + rising OI, stop 2 ATR1h, RR 2, 720m | combine the two pre-reasoned improvements (V06 exits + V09 filter) | ~ +0.12..0.15R on train; n too small for OOS bar |
| V14 | 1H displacement follow with LIMIT entry 0.25 ATR1h back from the close, valid 60m, maker fee; exits as V04 | cut entry cost and improve price; risk: adverse selection (only the failing moves fill) | ambiguous; if adverse selection dominates exp < V04 |

### Result V11-V14 (Train). Variants used: 14.

| id | n | exp R 1.0x [90% CI] | exp R 1.5x | PF | note |
|---|---|---|---|---|---|
| V11 | 1640 | -0.180 [-0.23,-0.13] | -0.270 | 0.72 | waiting for the reclaim bar does not rescue the cascade fade |
| V12 | 649 | -0.136 [-0.21,-0.06] | -0.210 | 0.76 | |
| V13 | 147 | +0.048 [-0.11,+0.21] | +0.006 | 1.10 | the two "improvements" do not stack (V09 +0.126, V06 +0.081) -> they were mostly noise |
| V14 | 326 | +0.043 [-0.07,+0.16] | -0.010 | 1.08 | limit entry saves cost (0.09R vs 0.13R) but adverse selection eats it |

(For V11/V12 the random baseline uses the 0.5 ATR floor stop rather than the structural stop, so it is not a like-for-like comparison; both are negative regardless.)

### Pre-registration V15-V16 (written BEFORE running; Train only)

New data-backed idea using the spot reference series: who led the displacement?
Perp premium over spot = fut close / spot close - 1 at 1H closes.
| id | rule | reasoning | prediction |
|---|---|---|---|
| V15 | 1H displacement where SPOT led (premium fell on an up-move / rose on a down-move); exits as V04 | spot-led = unlevered real demand (institutional/ETF-style flow) -> persists | V15 > V04 |
| V16 | 1H displacement where the PERP led (premium widened in the move direction) | leverage-led chase -> less continuation | V16 < V04 |

### Result V15-V16 (Train). Variants used: 16.

| id | n | exp R 1.0x [90% CI] | exp R 1.5x [90% CI] | PF | by year 2020/21/22/23 | note |
|---|---|---|---|---|---|---|
| V15 spot-led | 128 | **+0.282 [+0.09,+0.47]** | +0.202 [+0.01,+0.40] | 1.60 | -0.15/+0.20/+0.59/-0.07 | first variant to clear the expectancy bar on Train |
| V16 perp-led | 277 | -0.045 [-0.17,+0.08] | -0.126 | 0.92 | -0.12/-0.06/+0.16/-0.05 | ordering as predicted |

Cautions written immediately: (1) this is the best of 16 variants after 64 event tests — selection bias is large;
(2) only 31 trades/yr -> validation+holdout would give ~85 trades, below the 150 minimum -> INCONCLUSIVE by construction;
(3) negative in 2 of 4 full train years; 59% of quarters profitable (< 70% bar); 2022 and Jan-2024 (6 trades, +11R, ETF approval month) carry it.
(4) possible partial artefact: when spot has led, the perp may simply catch up a few bps in the next minutes (lead-lag), which is
real but would be tiny relative to the +34 bps gross per trade seen here.

### Pre-registration V17-V18 (redesign for sample size, as the brief requires). Train only.

Same logic, lower displacement threshold so that the OOS sample can reach 150 trades:
| id | rule | prediction |
|---|---|---|
| V17 | spot-led 1H displacement with range > 1.5 ATR1h (instead of 2.5); exits as V04 | ~3x trades; edge diluted but > 0 if the mechanism is real (dose-response: V15 > V18 > V17) |
| V18 | same with range > 2.0 ATR1h | in between |
If V17/V18 are ~0 the V15 result is most likely a small-sample peak.

### Result V17-V18 (Train). Variants used: 18.

| id | k | n | exp R 1.0x [90% CI] | exp R 1.5x [90% CI] | PF | q profitable |
|---|---|---|---|---|---|---|
| V17 | 1.5 | 351 | +0.051 [-0.06,+0.16] | -0.019 | 1.10 | 47% |
| V18 | 2.0 | 207 | +0.209 [+0.06,+0.36] | +0.137 [-0.01,+0.29] | 1.44 | 65% |
| V15 | 2.5 | 128 | +0.282 [+0.09,+0.47] | +0.202 [+0.01,+0.40] | 1.60 | 59% |

Monotone in the displacement threshold as predicted. V18 gives ~50 trades/yr -> ~135 OOS trades (just under 150); V17 has
enough trades but no edge after costs. There is no version with both enough trades and an edge.

**DEVELOPMENT PROGRESS NOTE:** 18 of 25 variants used. Dead on Train: cascade fades (V01-03, 07, 11, 12), sweeps (V05, V08),
plain displacement (V04, V06, V14), OI-conditioned (V09, V10, V13), perp-led (V16), loose spot-led (V17).
Alive on Train: spot-led 1H displacement follow, V15 (k=2.5) and V18 (k=2.0).

### Pre-registration: VALIDATION test of V15, V18 (and V16 as mechanism contrast). Written BEFORE running.

- Candidates are frozen as registered. No parameter is changed between Train and Validation.
- Predictions: if the mechanism is real, V15 and V18 have exp > 0 on validation and V16 < V15. Expected n: V15 ~40, V18 ~65.
- **Gate to the holdout (fixed now):** a candidate is frozen for the single holdout run only if, on Validation,
  exp > +0.15R at 1.0x AND exp > 0 at 1.5x AND it beats the random-entry baseline (p < 0.05) AND the +/- parameter
  perturbations on Train+Validation do not flip the sign. The 90% CI on ~50 trades cannot be expected to exclude 0, so CI > 0 is
  required only on the pooled OOS sample (Validation + Holdout) as the pass criteria state.
- If both pass the gate, V18 is the one frozen (more trades); if neither passes, the holdout is NOT run and the verdict is FAIL.

### VALIDATION RESULT (2024-02-08 .. 2025-05-31) — candidates FAIL

| id | n | exp R 1.0x [90% CI] | exp R 1.5x | PF | random mean (p) | q profitable |
|---|---|---|---|---|---|---|
| V15 spot-led k=2.5 | 71 | **-0.131** [-0.39,+0.15] | -0.227 | 0.81 | -0.20 (0.28) | 1/6 |
| V18 spot-led k=2.0 | 112 | **-0.225** [-0.42,-0.03] | -0.321 | 0.69 | -0.18 (0.70) | 1/6 |
| V16 perp-led (contrast) | 89 | 0.000 [-0.24,+0.25] | -0.088 | 1.00 | -0.20 (0.05) | 4/6 |

- Both candidates lose money on validation and are indistinguishable from random entries. The mechanism contrast reversed
  (perp-led >= spot-led). **The "spot-led displacement" Train result was a selection artefact (best of 18 variants) and/or
  specific to 2021-22. V15 and V18 are REJECTED. The gate to the holdout is not met.**

Diagnostic runs on validation (extra looks at validation, logged; not new variants):

| id | n | exp R 1.0x [90% CI] | exp R 1.5x | note |
|---|---|---|---|---|
| V04 plain displacement, 1 ATR / 240m | 160 | -0.058 [-0.23,+0.12] | -0.150 | Train was +0.058 |
| V06 plain displacement, 2 ATR / 720m | 143 | +0.116 [-0.04,+0.27] | +0.069 | Train was +0.081; beats random (p=0.02); 5/6 quarters positive |
| V01 cascade fade | 46 | -0.343 [-0.63,-0.03] | -0.418 | still dead |
| V08 trend sweep | 655 | -0.105 [-0.18,-0.03] | -0.204 | still dead |

Diagnosis of the failure: not costs (gross R of V18 on validation is itself -0.07), not too few trades, not look-ahead
(would inflate, not deflate): it is over-selection on Train. The only thing that looks the same on Train and Validation is the
weak, wide-stop continuation after a 1H displacement (V06: +0.08R train, +0.12R validation) — a small momentum effect,
below the +0.15R bar and with a CI that includes zero at 1.5x costs.

### Pre-registration V19-V20 (Train first). Variants used: 18 -> 20.

Hypothesis from the diagnosis: the continuation edge is real but small in bps, so only cost-in-R matters; longer holds and
letting winners run should raise net R. NOTE: V06's validation result has already been seen, so validation is no longer a
clean selector for this family; only Train results decide whether these go further, and the bar is the fixed one.
| id | rule | prediction |
|---|---|---|
| V19 | 1H displacement follow, stop 3 ATR1h, RR 2, time stop 1440m | cost ~0.05R; exp +0.08..0.14R; still under the bar |
| V20 | 1H displacement follow, stop 2 ATR1h, RR 3, time stop 720m | ~ V06 (few trades reach 3R in 12h) |
Gate: proceed only if Train exp > +0.15R at 1.0x and > 0 at 1.5x with 90% CI lower bound > 0 at 1.0x.

### Result V19-V20 (Train). Variants used: 20.

| id | n | exp R 1.0x [90% CI] | exp R 1.5x [90% CI] | PF | q profitable |
|---|---|---|---|---|---|
| V19 | 353 | +0.087 [-0.02,+0.19] | +0.059 [-0.04,+0.16] | 1.19 | 47% |
| V20 | 373 | +0.115 [+0.00,+0.23] | +0.072 [-0.04,+0.18] | 1.25 | 59% |

Neither meets the gate (exp > +0.15R). The 1H-displacement-follow family sits on a plateau of about +0.08..0.12R at 1.0x and
+0.04..0.07R at 1.5x regardless of exits (V06, V19, V20) — robust to perturbation, but too small.
`scripts/make_report.py` additionally ran V19/V20 on validation for a descriptive pooled table (extra validation looks, logged):
pooled Train+Validation V06 +0.091R [+0.01,+0.17] at 1.0x, +0.048R [-0.04,+0.13] at 1.5x.

### DECISION — loop stopped at 20 of 25 variants

- No variant passed Train + Validation + robustness. **The final holdout is therefore NOT run and was never downloaded**
  (`data/` contains no file for 2025-06 or later). It remains sealed and usable for future research.
- I stop at 20 variants rather than spend the last 5: every remaining idea I can think of is a re-parameterisation of something
  already tested, i.e. brute force, which the brief forbids.
- Verdict: **FAIL — no strategy with a positive-expectancy edge meeting the pre-set criteria was found.**

### Forward-test harness

`btcbot/forward.py`. Replay equivalence: feeding historical 1m bars one by one through the paper engine reproduces the
backtest trades exactly (tests/test_forward_replay.py; longer check in reports/forward_replay.json).
Live mode could NOT be run here: the sandbox proxy blocks `fstream.binance.com` (websocket) and `fapi.binance.com` (REST)
with HTTP 403. **Live paper trading has run for 0 days / 0 trades.**

## 2026-11-16 — Independent audit (separate sub-agent that did not write the code)

Scope: look-ahead, leakage, timestamps, fills, costs, statistics, holdout hygiene, log-vs-results consistency, and bugs that
could hide a real edge. It re-implemented the backtester and the event study independently from the raw parquet files.

Outcome: **no CRITICAL, no MAJOR findings.** Independent re-implementation reproduces V04/V06/V19/V20 trade-for-trade
(prices to 1e-11) and the event-study rows exactly. Holdout: no timestamp >= 2025-06-01 anywhere on disk or in git history.
All 42 feature columns and the signals of all 20 variants are unchanged when the future is randomised.

Minor findings and what I did:
| # | finding | action |
|---|---|---|
| 1 | funding window inclusive at both ends: a print at the entry bar's open (and at a time-exit bar's open) was charged | FIXED in `backtest.py` and `forward.py`, boundary tests added, **all variants re-run** |
| 2 | event-study volatility terciles were cut on the whole dev frame (Jan-2024 train rows used later-2024 vol) | FIXED (train rows only), **both event studies re-run** |
| 3 | validation was looked at beyond the gate (diagnostics V04/V06/V01/V08, pooled table V19/V20) | disclosed; validation is NOT out-of-sample for the displacement family; any future candidate must be judged on the holdout |
| 4 | pre-registration and previous results share commits, so ordering inside a commit is on trust | disclosed; cannot be fixed retroactively |
| 5 | feature cache had no invalidation (no result affected) | FIXED (cache keyed by hash of features.py) |
| 6 | random-entry baseline has 3-9% fewer trades and slightly different risk; auditor's same-times/random-direction baseline gives the same conclusions | disclosed |
| 7 | max drawdown is on closed-trade equity (understated); quarter stat counts the 1-month 2024Q1; Jan-2024 is a big share of train R for V04/V06 | disclosed in the report |
| 8 | truncation test is vacuous on sparse columns; missing boundary tests | funding/time-exit/short-gap tests added; the scramble test (the strong one) and the auditor's all-variants scramble cover the rest |
| 9 | small conservative simulator choices (false-negative direction, negligible) | left as is |

Effect of the fixes on results: max |change in expectancy| over all 54 variant/split/cost rows = 0.0018R; max |change in t| in the
event studies = 0.03. **No conclusion changed.** Numbers quoted earlier in this log are the pre-audit values (differences are in
the third decimal); `reports/variants.csv`, `reports/event_study*.md` and `FINAL_REPORT.md` hold the post-audit values.

## Multiple-testing counters (final)

- Event definitions tried: 16 (9 in Phase 0, 7 in Phase 0b) x 4 horizons = **64 tests**.
- Strategy variants tried: **20** of 25 allowed (V01-V20). Validation runs: 9 variant looks. Holdout runs: **0**.
