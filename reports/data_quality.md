# Data quality report (train+validation only)

## fut 1m klines
- range: 2020-01-01 00:00:00+00:00 .. 2025-05-31 23:59:00+00:00, grid minutes: 2,848,320
- duplicate rows: 0
- missing minutes (filled flat, flagged): 0 (0.0000%)
- number of gap runs: 0; longest:
- zero-volume real bars: 351
- OHLC-inconsistent bars: 0
- largest 1m |log return|: 0.0734 at 2020-03-13 02:40:00+00:00
- taker_buy_volume > volume rows: 0

## spot 1m klines
- range: 2020-01-01 00:00:00+00:00 .. 2025-05-31 23:59:00+00:00, grid minutes: 2,848,320
- duplicate rows: 0
- missing minutes (filled flat, flagged): 2,325 (0.0816%)
- number of gap runs: 15; longest:
  - 2020-02-19 11:36:00+00:00: 354 min
  - 2021-04-25 04:01:00+00:00: 284 min
  - 2021-08-13 02:00:00+00:00: 270 min
  - 2020-12-21 14:10:00+00:00: 230 min
  - 2020-06-28 02:00:00+00:00: 210 min
  - 2021-04-20 02:00:00+00:00: 150 min
  - 2020-04-25 02:00:00+00:00: 150 min
  - 2020-03-04 09:22:00+00:00: 128 min
  - 2021-09-29 07:00:00+00:00: 120 min
  - 2021-03-06 02:00:00+00:00: 90 min
  - 2023-03-24 12:40:00+00:00: 80 min
  - 2021-02-11 03:41:00+00:00: 79 min
  - 2020-12-25 02:00:00+00:00: 60 min
  - 2020-11-30 06:00:00+00:00: 60 min
  - 2020-02-09 02:00:00+00:00: 60 min
- zero-volume real bars: 211
- OHLC-inconsistent bars: 0
- largest 1m |log return|: 0.0751 at 2020-03-12 10:47:00+00:00
- taker_buy_volume > volume rows: 0

## funding
- 5934 prints 2020-01-01 00:00:00+00:00 .. 2025-05-31 16:00:00+00:00
- interval hours value counts: {8.0: 5933}
- mean 1.243 bps/8h, min -30.0, max 30.0

## metrics (open interest, 5m)
- 498,761 rows 2020-09-01 00:00:00+00:00 .. 2025-05-31 23:55:00+00:00
- missing 5m snapshots: 631 (0.126%)
- days with >=1 missing snapshot: 70; days fully missing: 0
- null oi rows: 0
