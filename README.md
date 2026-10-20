# BTC-Gated Momentum: Volatility-Filtered Breakout Research

**Independent quantitative strategy research | Python | October 2026**

A systematic, long-only cryptocurrency strategy investigating whether combining **Bitcoin trend confirmation**, **24-hour price breakouts**, and a **relative realised-volatility filter** can improve the selection of momentum trades. The model converts hourly OHLC data into ranked asset candidates and risk-bounded target portfolio weights.

> **Research status:** Signal construction and portfolio-target generation are implemented. A fully reproducible, fee-adjusted historical *portfolio* performance report is being prepared. Performance cells marked `TBD` have intentionally not been estimated or attributed to this strategy without supporting evidence.

## At a glance

| Component | Specification |
| --- | --- |
| Strategy name | `btc_gated_momentum` |
| Frequency | Hourly, using completed candles |
| Direction | Long only |
| BTC filter | Latest BTC close above its 48-hour simple moving average |
| Entry candidate | Latest close exceeds highest high of the prior 24 hourly candles |
| Volatility condition | Current 24-hour realised volatility below the median of the previous 168 estimates |
| Ranking | Highest trailing 24-hour return among qualifying candidates |
| Positioning | Up to 3 assets, 10% target weight per asset |
| Maximum targeted exposure | 30%; remaining 70–100% in cash |
| Output | Portfolio target weights; **no orders placed by the research signal script** |

## 1. Research question and hypothesis

**Research question:** Can BTC trend confirmation and low *relative* realised volatility help filter 24-hour upside breakouts in cryptocurrency markets?

The research begins with three observations:

1. **Breakout momentum:** A closing price above a recent trading range may signal persistent buying interest, but false breakouts are common.
2. **Market context:** Altcoin momentum may be sensitive to the broader direction of Bitcoin, so BTC serves as a simple market gate.
3. **Relative volatility:** Comparing an asset's current volatility with its own recent distribution may help distinguish breakouts occurring under different risk conditions.

**Hypothesis:** Requiring a supportive BTC trend and below-median relative volatility may improve the quality of momentum-based candidate selection compared with an unfiltered breakout rule. This remains a hypothesis to evaluate rather than a claim of established trading alpha.

**Scope:** This is hourly systematic trading research, not high-frequency trading, market making, or arbitrage.

## 2. My individual contribution

I independently formulated the central trading hypothesis and designed the primary **BTC-gated momentum** signal and portfolio-construction rules, including:

- A BTC trend gate based on a 48-hour simple moving average.
- A prior-24-hour high breakout condition, excluding the current candle from the reference range.
- A relative-volatility condition using a 24-hour rolling estimate and the previous 168 estimates as its historical comparison window.
- Cross-asset ranking using trailing 24-hour returns.
- Long-only portfolio targets capped at 10% per selected asset and 30% aggregate target exposure.
- Python-based signal generation, input validation, and structured target-weight output as documented below.

This repository focuses on **the independent signal research and evaluation**. It does not claim authorship of the team's separate trading bot, execution infrastructure, or other members' analysis.

## 3. Trading universe and portfolio design

`BTC/USD` is used as the **reference market**, not a selected position in the provided signal implementation.

The research signal's documented default eligible universe is:

`ETH/USD`, `DOGE/USD`, `SHIB/USD`, `PEPE/USD`, `FLOKI/USD`, `BONK/USD`.

The set is configurable using the script's `--pairs` option. It is a predefined research universe, **not** a dynamic liquidity or market-capitalisation screen. Availability and tradability require separate checks in an execution system.

| Rule | Implementation |
| --- | --- |
| Maximum positions | 3 |
| Target allocation per selected asset | 10% of portfolio |
| Maximum combined asset allocation | 30% |
| Unallocated weight | Held as cash target |
| Fewer than 3 qualified assets | Do not redistribute unused allocation |
| No qualified assets or BTC gate fails | 100% cash target |

These constraints bound *intended exposure*, not actual live holdings or realised drawdowns.

## 4. Strategy methodology

Let $C_{i,t}$ and $H_{i,t}$ denote the close and high of asset $i$ at completed hourly candle $t$.

### 4.1 BTC regime gate

Allow candidate selection only when:

$$
C_{\mathrm{BTC},t}>\frac{1}{48}\sum_{j=0}^{47}C_{\mathrm{BTC},t-j}.
$$

If the condition is not met, the strategy outputs zero target allocation for all eligible altcoins.

### 4.2 Breakout confirmation

Require the current completed candle's close to exceed the **highest high of the previous 24 candles**:

$$
C_{i,t}>\max(H_{i,t-1},\ldots,H_{i,t-24}).
$$

The current candle is deliberately excluded from the breakout reference window.

### 4.3 Relative realised-volatility screen

Calculate hourly log returns:

$$
r_{i,t}=\ln\left(\frac{C_{i,t}}{C_{i,t-1}}\right).
$$

Compute the sample standard deviation of the latest 24 hourly log returns:

$$
v_{i,t}=\operatorname{SD}(r_{i,t-23},\ldots,r_{i,t}).
$$

Require:

$$
v_{i,t}<\operatorname{Median}(v_{i,t-1},\ldots,v_{i,t-168}).
$$

The benchmark excludes the current volatility estimate. This tests **low volatility relative to recent history**, not a continuously declining volatility trend.

### 4.4 Ranking and target construction

For candidates satisfying all filters, calculate trailing 24-hour simple return:

$$
R_{i,t}^{24h}=\frac{C_{i,t}}{C_{i,t-24}}-1.
$$

Rank qualified assets by descending return, select up to three, and set each selected asset's target weight to **0.10**. All remaining weight is assigned to cash.

The portfolio targets are **signals**; they do not imply that an exchange order has been submitted or filled.

## 5. Python implementation

The implementation described in the original research notes is `vol_contraction_signal.py`, with the principal function:

```python
latest_targets(candles, allowed_pairs)
```

> **Repository maintenance note:** If the published file is renamed to `btc_gated_momentum.py`, update the command below and all references to match the actual committed filename. The strategy label `btc_gated_momentum` does **not** by itself establish that such a file exists.

The code uses `pandas` and `numpy` for rolling indicators, signal checks, ranking, and weight generation. Its key expressions include:

| Expression | Purpose |
| --- | --- |
| `btc.rolling(48).mean()` | BTC trend reference |
| `high.shift(1).rolling(24).max()` | Previous-high breakout threshold |
| `np.log(close / close.shift(1)).rolling(24).std()` | 24-hour realised volatility |
| `rv24.shift(1).rolling(168).median()` | Historical relative-volatility benchmark |
| `close / close.shift(24) - 1` | Momentum ranking |
| Top-three selection and fixed weights | Target portfolio construction |

### Input data

Provide a long-format CSV containing:

```text
timestamp,pair,open,high,low,close
```

The documented signal validator expects UTC **candle-start timestamps**, completed and recent hourly bars, strictly positive numeric price fields, no missing or duplicate timestamps, and synchronised series across included markets. The documented minimum is **220 contiguous hourly observations** per included market, including BTC. Invalid or stale input may produce a validation error instead of a signal.

### Output

A structured JSON object containing fields such as:

```text
signal_as_of_completed_candle_utc
btc_uptrend
target_weights
ranked_entries
cash_target_weight
mode = "SIGNAL_ONLY_NO_TRADES"
```

### Running the signal script

```bash
pip install numpy pandas
python vol_contraction_signal.py --csv hourly_ohlc.csv
```

To specify a smaller research universe:

```bash
python vol_contraction_signal.py --csv hourly_ohlc.csv --pairs ETH/USD DOGE/USD PEPE/USD
```

**Important:** This script validates freshness against the current clock, so an older historical CSV cannot simply be supplied to it for backtesting. A chronological backtest needs a controlled simulation clock or a separately implemented historical engine.

## 6. Historical evaluation

The objective of backtesting is to test whether the hypothesis survives transaction costs and changes in market conditions. Backtesting **does not** retroactively explain or reproduce the hackathon leaderboard result.

### 6.1 Historical Backtesting

The original BTC-Gated Momentum strategy combines Bitcoin market-regime filtering, 24-hour price breakouts, realised-volatility contraction and cross-asset momentum ranking.

Historical experiments used Binance hourly cryptocurrency data and compared the strategy against four alternative momentum-based approaches.

Best observed exploratory result: +0.896% final-period return, with 0.363% maximum drawdown, in an earlier six-hour rebalancing simulation using a 0.20% estimated execution cost per side.

This result is reported as an exploratory observation rather than verified out-of-sample profitability. Subsequent tests using different simulation assumptions and historical samples produced negative returns.

The research illustrates the sensitivity of systematic trading performance to execution assumptions, rebalancing frequency and sample selection. Historical Binance results do not represent realised returns from the Roostoo competition.


| Metric | Standalone strategy backtest |
| --- | --- |
| Data source | **TBD — insert provider and dataset reference** |
| Historical period | **TBD — insert start/end dates (UTC)** |
| Eligible assets actually tested | **TBD — insert universe** |
| In-sample / validation / held-out periods | **TBD — insert chronological split** |
| Gross total return | **TBD** |
| Net total return | **TBD** |
| Sharpe ratio | **TBD — recalculate from periodic net portfolio returns** |
| Sortino ratio | **TBD** |
| Calmar ratio | **TBD** |
| Maximum drawdown | **TBD** |
| Number of trades | **TBD** |
| Portfolio turnover | **TBD** |
| Fees, spreads and slippage | **TBD — state actual assumptions** |
| Benchmark return | **TBD — specify benchmark** |

**To insert:** a labelled equity curve, drawdown chart, trade count and reproducibility instructions, once generated and verified.

### 6.2 Evaluation protocol

A defensible portfolio simulation should:

1. Use only information observable by the end of candle $t$ to compute its signal.
2. Simulate execution no earlier than a subsequent executable price, not the same candle's retrospectively known close.
3. Track cash and holdings through time, including exits when target weights fall to zero.
4. Include explicit transaction fees, bid–ask spread and slippage assumptions, and show sensitivity to those assumptions.
5. Reserve a chronological held-out segment, without tuning parameters on the final test results.
6. Publish the observation period, return frequency, trade count, and actual backtest implementation so results can be reproduced.

### 6.3 Risk-adjusted metrics — pending calculation

- **Sharpe:** mean periodic excess portfolio return divided by its standard deviation, annualised using the stated return frequency.
- **Sortino:** excess return over a stated target relative to downside deviation.
- **Calmar:** annualised compounded return divided by the absolute maximum drawdown, where the observation period supports a meaningful estimate.

Use a consistent **net-of-cost portfolio-equity series** for these calculations. If a statistic is undefined or misleading due to sample size or a zero denominator, report that directly rather than inserting a fabricated number.

## 7. Market-regime sensitivity research

The companion research investigated whether results differed across **BTC uptrend, sideways, downtrend and high-volatility conditions**. The historical regime classification described in the original notes used BTC 24-hour and 168-hour moving averages and a realised-volatility threshold derived from training data.

This analysis is **diagnostic and descriptive**: it does not itself change the strategy's live target allocations.

### Interpretation

Initial regime comparisons identified **weaknesses and negative returns in several research and validation subsets**, supporting further investigation of regime dependence and false breakouts. The currently available README also reports some positive results in its *final-test* regime subsets, so the full table must be reconciled against the underlying CSV before a single definitive summary is published.

The practical research takeaway is that **regime sensitivity deserves testing, and no consistently profitable regime has yet been established across evaluation periods**. Negative findings are retained as evidence rather than edited out.

**To verify before publishing detailed figures:**

- [ ] Confirm the exact strategy identifier in the regime CSV (`btc_gated_momentum` versus prior research labels).
- [ ] Reconcile research / validation / final-test observations against the latest generated CSV.
- [ ] Confirm that reported returns reflect portfolio accounting and the declared trading-cost assumptions.
- [ ] Insert a small table or plot of **verified** regime results, including negative values.
- [ ] Confirm that high-volatility group sizes are adequate to interpret.

**Optional supporting documentation:** link to a verified regime analysis file once it exists at the committed relative path (for example, `Market_regime_research/README.md`).

## 8. Risk management and limitations

**Implemented at the signal level**

- Long-only selection and BTC market gate.
- Maximum three selected positions.
- Fixed 10% allocation per selected asset, with 30% maximum aggregate **target** exposure.
- Cash target for unused allocation.
- Required completed, recent and synchronised market data; rejection of selected invalid inputs.

**Not established by the signal script**

- Successful live order placement, fills, position reconciliation or execution quality.
- Standalone stop-loss, take-profit or intrabar liquidation rules.
- Protection against false breakouts, crypto-asset correlation, thin liquidity, or spread widening.
- Historical profitability or satisfactory risk-adjusted performance.

The original notes also identify data checks that could be extended, including OHLC internal-consistency validation and enforcement of exact hour-boundary timestamps.

## 9. Hackathon context — separate from strategy performance

This research originated during the **HK vs AU vs IN Quant Trading Hackathon (October 2026)**. The team reached **9th among 190 teams (top 5%)**, according to the reported leaderboard placement. **[ADD: link or screenshot of the final official ranking, and verify final versus interim status.]**

My individual contribution was the core research hypothesis and signal/portfolio model documented here. The team's separately developed live execution bot was **not a faithful end-to-end implementation of this research universe and strategy**, and executed very few trades during the competition. As a result, the leaderboard placement **must not be interpreted as measured live returns attributable to this standalone model**.

This repository intentionally does not include or claim authorship of the team bot. Live contest metrics are not presented as a backtest of `btc_gated_momentum`.

## 10. Next research steps

- [ ] Commit and verify the standalone strategy source and input-data example (with no credentials or private data).
- [ ] Implement / document a reproducible, chronological portfolio backtest using the intended universe.
- [ ] Calculate **net return, Sharpe, Sortino, maximum drawdown, trade count and turnover** from a consistent portfolio return series.
- [ ] Compare breakout-only, breakout + BTC gate, breakout + volatility screen and the full combined model on the same sample.
- [ ] Reconcile market-regime CSV labels and figures, retaining negative results.
- [ ] Run robustness checks for nearby lookback windows, costs, universe selection and out-of-sample performance.
- [ ] Add a final leaderboard evidence link and a clearly labelled backtest chart.

---

**Research integrity note:** The purpose of this repository is to document strategy design, implementation and empirical evaluation. A high hackathon ranking is a team competition outcome, not independent evidence that this particular strategy was profitable in live trading. Any future numerical results should be supported by reproducible code, data and stated assumptions.
