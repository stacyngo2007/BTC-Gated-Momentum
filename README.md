# BTC-Gated Momentum

**Systematic trading strategy research | Python · pandas · NumPy | October 2026**

Independent research and implementation of a long-only cryptocurrency momentum strategy combining a **Bitcoin market-regime gate**, **24-hour price breakouts**, and **relative realised-volatility screening**. The project produces risk-bounded portfolio targets and evaluates the hypothesis using historical Binance spot data.

> **Project scope:** This repository documents my independent strategy research and subsequent historical simulation. The signal module does **not** place orders. A separate team-built execution system was responsible for competition trades; historical Binance results are **not** Roostoo realised performance.

## At a glance

| Feature | Design |
| --- | --- |
| Market regime | BTC close above its 48-hour simple moving average |
| Breakout | Asset close above the highest high of the previous 24 completed candles |
| Volatility screen | Latest 24-hour realised volatility below the median of the **preceding** 168 estimates |
| Ranking | Descending trailing 24-hour return |
| Portfolio | Long-only; up to three assets at 10% target weight each |
| Exposure | At most 30% invested; unused weight held in cash |
| Signal data | Completed, synchronised hourly OHLC observations |
| Historical experiment | Signals reviewed and portfolio targets updated at six-hour intervals |

## Research hypothesis

A simple price breakout may produce false positives when the broader cryptocurrency market is weak or an individual asset is experiencing elevated volatility. I investigated whether requiring **(1) a positive BTC trend** and **(2) below-median relative realised volatility** could improve the selection of momentum candidates versus a basic 24-hour breakout benchmark.

The hypothesis is an empirical question, not a claim of established trading alpha.

## Strategy construction

For each signal evaluation, using the latest completed hourly candle:

1. **Apply the market gate.** Permit long entries only when BTC closes above its trailing 48-hour simple moving average.
2. **Identify breakouts.** Require a candidate asset's close to exceed the highest *high* of the previous 24 candles; the current candle is excluded from the comparison.
3. **Screen relative volatility.** Calculate the sample standard deviation of the latest 24 hourly log returns. Require it to be below the median of the previous 168 rolling-volatility estimates (excluding the current estimate).
4. **Rank and allocate.** Rank eligible assets by 24-hour percentage return. Select up to three and allocate 10% target weight to each. Hold the balance in cash; do not redistribute unused slots.

BTC is a reference market, not a tradable position in the provided signal implementation. The default candidate universe is ETH, DOGE, SHIB, PEPE, FLOKI and BONK, quoted against USD in the signal interface. The Binance research experiment uses corresponding **USDT-quoted proxy markets**, which are not identical to Roostoo USD quotes.

### Signal validation and safety

`strategy.py` rejects missing or non-positive OHLC values, duplicate pair/timestamp records, missing BTC reference data, unsynchronised markets, gaps in the hourly time series and insufficient observations. In normal signal mode, it also rejects incomplete or stale latest candles. It returns **target weights only**—no API credentials, trading orders or autonomous execution.

## Historical backtesting

`backtesting_6h_exploratory.py` evaluates five research variants using approximately 120 days of Binance spot hourly data: a 24-hour breakout benchmark, a 72-hour breakout, 72-hour and 168-hour relative-strength models, and the volatility-contraction breakout described above.

The experiment evaluates signals with a six-hour rebalancing schedule, applies positions from the **following** hourly open, and uses an approximate weight-based portfolio-return calculation. The experiment evaluates signals using a six-hour rebalancing schedule, applies target positions from the following hourly open, and uses approximate weight-based portfolio accounting. An estimated 0.20% cost per side is applied to traded notional to approximate transaction fees and slippage. The simulation does not separately model bid–ask spreads, market impact, order-book liquidity, partial fills, or drift-aware cash-and-holdings accounting.

### Selected exploratory result

An **earlier historical run** of the volatility-contraction breakout produced:

| Metric | Earlier six-hour exploratory run |
| --- | ---: |
| Final-period simulated return | **+0.896%** |
| Simulated P&L on $50,000 | **+$448.06** |
| Final-period maximum drawdown | **0.363%** |
| Final-period Sharpe ratio | **4.480** |
| Assumed total execution cost | **0.20% of traded notional per side** |

**Interpretation:** These figures are a *previously observed exploratory outcome*, **not** verified or reproducible out-of-sample performance, and **not** realised competition P&L. Other runs and evaluation configurations produced negative returns. This run was observed during iterative research, so selecting it retrospectively does not establish predictive skill.

**Reproducibility note:** The six-hour research script downloads a rolling 120-day historical window, so the market sample and evaluation boundaries change between executions. Although the published script uses the same 0.20%-per-side cost assumption, the retained results CSV and equity chart may represent a different historical run from the +0.896% observation. Reproducing that earlier result would require the exact historical data and evaluation dates used at the time.

The retained numerical output, where provided, is available at [`crypto_three_strategy_results/all_strategy_metrics.csv`](crypto_three_strategy_results/all_strategy_metrics.csv), along with the [equity-curve chart](crypto_three_strategy_results/equity_curves.png). Those artifacts document their own run; they are not evidence for the earlier +0.896% snapshot.

## Repository structure

```text
BTC-Gated-Momentum/
├── strategy.py                         # Validated, signal-only target allocation model
├── backtesting_6h_exploratory.py       # Six-hour historical research simulation
├── requirements.txt
├── README.md
└── crypto_three_strategy_results/
    ├── all_strategy_metrics.csv        # Retained experiment metrics
    └── equity_curves.png               # Retained experiment chart
```

### Run the research code

```bash
pip install -r requirements.txt
python backtesting_6h_exploratory.py
```

The historical runner fetches Binance data over the network and writes results into `crypto_three_strategy_results/`. Its output may differ from previously saved figures because the download window rolls forward.

To run the **standalone signal generator**, provide a CSV of completed, contiguous hourly candles with the following columns:

```text
timestamp,pair,open,high,low,close
```

```bash
python strategy.py --csv hourly_ohlc.csv
```

The signal script checks data freshness for normal use. It requires at least 220 synchronised hourly observations and returns a JSON object containing the BTC regime flag, ranked candidates, target weights and target cash weight. It does not execute trades. The CLI filename is `strategy.py`; `backtesting_6h_exploratory.py` is a separate vectorised research implementation.

## Individual contribution and hackathon context

I independently developed the **BTC-gated breakout and volatility-contraction research hypothesis**, Python signal-generation logic, asset-ranking method and capped portfolio target construction. I subsequently investigated it through historical simulation and benchmark comparisons.

This work was undertaken in the context of the **HK vs AU vs IN Quant Trading Hackathon**, where my **team placed 9th among 190 teams (top 5%)**. The team ranking is a **collective competition outcome**, not evidence that this particular model earned the leaderboard return. Order execution and bot infrastructure were developed separately; this repository does not claim authorship of those components.

## Limitations and next steps

- **Sample dependence:** Moving data windows and short chronological segments can materially change observed returns.
- **Selection bias:** The positive exploratory run was identified after examining multiple outcomes; it is not an untouched holdout result.
- **Execution simplification:** The six-hour simulator approximates weight-based returns and does not model live fills, order-book spreads, partial fills or liquidity constraints.
- **Market mismatch:** Historical Binance USDT candles are proxies, not Roostoo market prices or a replay of the competition.
- **Risk:** Long-only crypto assets may be correlated, and a 30% target exposure cap does not guarantee limited realised losses.

For stronger evidence, freeze the data window, archive the input data and parameter settings, test execution-cost sensitivity and evaluate a genuinely unseen forward period without selecting configurations using that period's results.

---

**Research integrity:** The project demonstrates strategy formulation, signal engineering, risk-bounded portfolio construction and critical assessment of historical evidence. Exploratory simulation results should not be interpreted as guaranteed or live trading profitability.
