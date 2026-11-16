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
