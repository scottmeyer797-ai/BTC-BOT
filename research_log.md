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
