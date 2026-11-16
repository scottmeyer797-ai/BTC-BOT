# Prompt for Fable 5.2: Autonomous Liquidity / Institutional-Footprint Strategy Research

Copy everything below the line into a new session with the repo attached.

---

## Role and goal

You are an autonomous quantitative researcher. Design, test and honestly evaluate an intraday Bitcoin strategy that tries to detect and follow **institutional liquidity-driven moves** (stop sweeps, liquidity raids, forced liquidations, displacement). It cannot move price itself. It can only detect footprints of large flow and trade with them. The goal is **a truthful verdict on whether a strategy has a real, positive-expectancy edge after realistic costs**, not a profitable-looking backtest. A clear "no edge found" is a successful outcome if it is backed by evidence.

You have full freedom to invent the strategy from your own logic. For inspiration only, I like rule-based, multi-timeframe scalping (higher-timeframe structure and bias, then a lower-timeframe trigger, key session windows such as the London and New York opens, fixed stop and fixed reward-to-risk). You may use that style, combine it with other ideas, or ignore it if the data points elsewhere. Do not copy any course or influencer system; derive and justify your own rules.

## Hard constraints

- **No real money. No live order placement.** Research and paper trading only.
- Work only in this repo, on branch `claude/forex-trading-bot-ge2nla`. Commit often. Do not open a PR unless I ask.
- Never put API keys in code or commits. Read them from environment variables, and tell me which ones you need.
- Do not fabricate data or results. Every number in the report must come from code that is committed and re-runnable.

## How to work

- Work autonomously. Do not stop to ask me about choices you can reasonably make yourself. Ask only when truly blocked (for example network access, missing credentials) and say exactly what you need.
- Checkpoint: commit after every meaningful step, keep `research_log.md` current, and make long jobs resumable. Make every result reproducible from a seed and a single documented command.
- Post a short progress note at the end of each phase (Phase 0, development, validation, holdout).
- Use sub-agents where useful, for example to run independent event studies in parallel and for the independent audit described below.
- Prefer simple, interpretable rules. Machine-learning models are allowed only if they pass the same protocol, and you must explain why they should work.

## Instrument and data (Bitcoin only)

Trade **BTCUSDT** (perpetual futures primary, spot for reference). No other market in this test.

- **Primary data source:** Binance public data archive, `https://data.binance.vision` (free, no API key). Use 1-minute klines, aggTrades (to compute buy/sell aggression and delta), funding rates, and open interest/metrics. Check whether liquidation data exists for the period and use it only if complete. Use the `ccxt` library for anything not in the archive.
- **Period:** from the earliest clean perpetual-futures data (about 2020) to the most recent complete month. Download once, store as Parquet in `data/` (git-ignored, with a download script committed).
- **Fallbacks:** if `data.binance.vision` is blocked, tell me which host to allow. If Binance is unavailable in this environment, use Coinbase or Bybit public data and say so.
- **Data quality:** check gaps, duplicates and outages, and document them. Note that BTC trades 24/7, so define sessions explicitly (Asia, London, New York by UTC hours).
- **Known BTC risks to model:** funding payments, exchange fees (taker and maker), slippage, liquidation-driven volatility, and regime changes (2020-21 bull, 2022 bear, post-2024 ETF era).
- You may use open-source tools from GitHub (for example `vectorbt`, `backtesting.py`, `ccxt`) but you must verify their fill and cost assumptions and write unit tests for look-ahead bias.

**Out-of-sample testing lives in the same dataset.** Split the one dataset by time as described in the protocol below: Train 60%, Validation 20%, Final holdout 20% (the most recent period). There is no separate repo for out-of-sample data.

## Phase 0: Event study (before any strategy)

1. Define 4-6 "institutional footprint" events as **exact, testable code**, for example: sweep of previous-day or session high/low followed by a close back inside; equal-highs/lows raid; displacement candle (range > k x ATR) that breaks structure; liquidation cascade (BTC); delta divergence at a level (futures); fix- or open-time moves.
2. For each event, collect every occurrence in the Train data and measure forward returns (5, 15, 30, 60 min) net of costs, versus a **matched random baseline** (same time of day, same volatility regime). Report effect size, confidence interval and sample size.
3. Only events with a statistically credible edge may become strategy components. Report the events that had **no** edge too, as that is a valuable finding.
4. Count every event definition tried toward the multiple-testing total.

## Data handling

Use at least **3 years** of 1-minute data (aim for 5+). Resample to 5m, 15m and 1H yourself. Report what you chose, its limits, and what you could not access.

## Cost model (mandatory, conservative)

Model spread or tick cost, exchange fees, slippage on entries and stops, funding costs (crypto perpetuals), and commission. Use **conservative** numbers and say what they are. Also run every final test at **1.5x costs** as a stress test. With tight scalping stops, costs decide everything, so test this early.

## Protocol to prevent self-deception

Follow this exactly. It is the most important part of the task.

1. **Split the data by time before looking at any results:**
   - **Train/Development: first 60%**, for exploring and building.
   - **Validation: next 20%**, for choosing between candidate strategies and tuning.
   - **Final holdout: last 20%.** **Do not touch it, load it, or plot it until I would be ready to read the final verdict.** Commit the split dates to the repo *before* any backtest so the split is provably fixed. **Enforce this in code:** do not download or load the holdout period until the freeze step, and make the data loader refuse holdout dates unless an explicit `--final-holdout` flag is set. Leave a gap (embargo) of at least a few days between splits so trades and features cannot straddle a boundary.
2. **Keep a research journal** (`research_log.md`) with every hypothesis, parameter set and result, including failures. Count every variant you try. This is your multiple-testing count, and it has to be reported.
3. Develop on Train. Confirm on Validation. Use **walk-forward** testing (rolling re-fit and test) rather than one static split where possible.
4. **Run the Final holdout exactly once, on one frozen strategy.** If it fails, you may not tweak and re-run on that same holdout. A failed holdout means the strategy is rejected.
5. Judge by **net expectancy per trade in R, after costs**, not win rate. Also report profit factor, max drawdown, trade count, Sharpe or Sortino, longest losing streak, performance by year and by session, and a Monte Carlo or bootstrap confidence interval on expectancy.
6. **Robustness checks:** small parameter perturbations should not flip the result. Edge should hold across regimes and years, and at 1.5x costs. A strategy that only works on one narrow parameter peak is overfit.
7. Adjust for multiple testing. With N variants tried, a good-looking best result is expected by chance. Report a deflated Sharpe or a simple Bonferroni-style haircut, and say how much of the result survives.

## Baselines and fill realism

- Every strategy must beat **(a)** random entries with the same stop, target, holding time and trade frequency, and **(b)** buy-and-hold, on the same period and risk. BTC's long uptrend makes long-biased results look good by default, so also report long and short results separately.
- Fills must be conservative: market orders fill at the next bar's open or worse plus slippage. Limit orders fill only if price trades *through* the level, never merely touches it. Stops fill with slippage and gap risk. Use real funding timestamps. Cap leverage and check that the position would not be liquidated.

## Independent audit (before the holdout run)

Before the single holdout run, spawn a separate sub-agent that did not write the code. Its only job is to find look-ahead bias, leakage, survivorship or timestamp errors, unrealistic fills and any peeking at the holdout. Fix what it finds, log it, and rerun the affected results before proceeding.

## Pass criteria (decide these now and do not move them later)

A strategy passes only if, on **out-of-sample data (Validation and Final holdout)**, at 1.0x and 1.5x costs:
- Net expectancy > **+0.15R per trade**, with the lower bound of the 90% bootstrap confidence interval above 0.
- At least **150 out-of-sample trades** (otherwise say "inconclusive", not "pass"). Check early that the strategy can plausibly produce that many trades in the Validation and holdout periods. If it trades too rarely to ever reach this, say so and redesign rather than accept a thin sample.
- Beats both baselines above.
- Profit factor > 1.2 and max drawdown acceptable at 1% risk per trade.
- Profitable in at least 70% of calendar quarters and across different market regimes (bull, bear, sideways).

## The loop (autonomous, with a limit)

1. Form a hypothesis (with a market-logic reason, not just a pattern). **Write the hypothesis and the exact prediction in `research_log.md` and commit it before running the test.** Then code it, backtest on Train, and log the result.
2. If Train looks promising, test on Validation. If Validation fails, **diagnose why** (costs? overtrading? regime dependence? look-ahead bias? too few trades?) and form a new hypothesis. Do not just brute-force parameters.
3. Make at most **25 strategy variants in total**. After that, stop and report, even if nothing passed.
4. Only a strategy that passes Train, Validation and robustness gets a single run on the Final holdout.
5. Test for **look-ahead and leakage bugs** before trusting anything. Signals must use only bars that closed before the entry. Entry fills happen on the next bar or tick. Write unit tests for this.

## Forward testing (paper, no real money)

- A backtest is not live testing. Build a **forward-test harness** that streams live BTCUSDT data from Binance's public websocket feed (no account needed), generates signals in real time with the same code as the backtest, and logs **hypothetical** fills using the same conservative cost and fill model. It must never place real orders and must not need trading API keys.
- Test the harness first by replaying historical data and checking it produces the same signals as the backtest. Document how I start it, and where the log is written.
- Do not claim live results unless it actually ran live. Say how many days or trades it has run.

## Deliverables

1. Clean, tested Python repo with a clear structure (data, features, strategy, backtester, costs, reporting, forward-test).
2. `research_log.md`: the full journal including every failed idea.
3. `FINAL_REPORT.md` with:
   - A plain-English verdict first: **PASS / FAIL / INCONCLUSIVE**.
   - The final rules, written so a human could trade them by hand.
   - Equity curves and tables for Train, Validation and Holdout at 1.0x and 1.5x costs.
   - The number of variants tried and the multiple-testing adjustment.
   - Known weaknesses, data limits, and what could still be wrong.
   - A recommended next step (paper trading, more research, or abandon).
4. A short summary at the top of your final message, with the verdict and the 3 most important numbers.

## Honesty rules

- Report negative results as clearly as positive ones.
- If you are unsure whether a result is real, say so. Never round a failure into a success.
- If you find a bug that invalidated earlier results, tell me and redo the affected work.
- If you hit the 25-variant limit with no passing strategy, say that. Do not quietly start over with the holdout in mind.
