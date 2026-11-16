# BTC Bot — research: do "institutional liquidity footprints" give an intraday BTC edge?

**Verdict: FAIL / no edge found.** See [`FINAL_REPORT.md`](FINAL_REPORT.md) and the full journal [`research_log.md`](research_log.md).
Research and paper trading only. Nothing in this repo can place an order; no API keys are used anywhere.

## Layout
| path | what |
|---|---|
| `config/splits.json` | train / validation / holdout dates (committed before any backtest) |
| `scripts/download_data.py` | Binance public archive -> `data/*.parquet` (refuses holdout months without `--final-holdout`) |
| `btcbot/data.py` | loaders with a hard holdout guard |
| `btcbot/features.py` | causal 5m / 1H features from 1m bars |
| `btcbot/events.py` | exact event definitions (sweeps, raids, displacement, cascade proxy, delta divergence, open drives) |
| `btcbot/strategy.py`, `btcbot/variants.py` | signal generator and the registry of all 20 variants |
| `btcbot/backtest.py`, `btcbot/costs.py` | 1m event-driven simulator, conservative fills and costs |
| `btcbot/stats.py`, `btcbot/evaluate.py` | metrics, bootstrap, random-entry and buy-and-hold baselines, deflated Sharpe |
| `btcbot/forward.py` | paper forward-test harness (live websocket or historical replay) |
| `tests/` | fill-model, look-ahead, holdout-guard and replay-equivalence tests |
| `reports/` | generated tables, trade lists, equity curves |

## Reproduce everything (seed in `config/splits.json`)
```bash
pip install -r requirements.txt
python scripts/download_data.py          # train + validation only (~400 MB)
python scripts/data_quality.py
python -m pytest -q tests
python scripts/event_study.py 0 && python scripts/event_study.py 0b
python scripts/run_variant.py V01 V02 V03 V04 V05 V06 V07 V08 V09 V10 V11 V12 V13 V14 V15 V16 V17 V18 V19 V20 --split train
python scripts/run_variant.py V15 V18 V16 V04 V06 V01 V08 V19 V20 --split validation
python scripts/make_report.py
```
The holdout (2025-06-08 .. 2026-10-31) has never been downloaded or run. Doing so needs the explicit
`--final-holdout` flag on both the downloader and the runner.

## Paper forward test
```bash
python -m btcbot.forward --replay 2023-01-10 2023-02-10 --variant V06   # replay check vs backtest
python -m btcbot.forward --live --variant V06                            # live paper trading
```
Live mode needs outbound access to `fstream.binance.com` (websocket) and `fapi.binance.com` (REST warm-up and funding).
Logs: `forward_logs/<variant>_signals.csv`, `forward_logs/<variant>_paper_trades.csv`. No environment variables or keys are needed.
