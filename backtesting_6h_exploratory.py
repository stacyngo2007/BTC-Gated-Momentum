"""Research-only Binance spot backtest: five momentum strategy variants.
Run: python backtesting_6h_exploratory.py
Dependencies: pip install pandas numpy requests matplotlib
No API keys and NO order requests. Uses real Binance SPOT hourly OHLCV.
Signals use completed closes. Positions change at the NEXT hourly open.
"""
from pathlib import Path
import time
import numpy as np
import pandas as pd
import requests

SYMBOLS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT"]
TRADED = [s for s in SYMBOLS if s != "BTCUSDT"]
INITIAL_CAPITAL = 50_000.0
DAYS_HISTORY = 120
FEE_AND_SLIPPAGE_PER_SIDE = 0.002  # Estimated 0.20% execution cost per side
MAX_EXPOSURE = 0.30
MAX_POSITIONS = 3
REBALANCE_HOURS = 6
OUTPUT_DIR = Path("crypto_three_strategy_results")
BASE = "https://api.binance.com/api/v3/klines"
SESSION = requests.Session()


def fetch_hourly(symbol, days=DAYS_HISTORY):
    # Page backwards to avoid the 1000-bar per-request limit.
    end_ms = int(time.time() * 1000)
    begin_ms = end_ms - days * 24 * 3600 * 1000
    collected = []
    cursor = end_ms
    while cursor > begin_ms:
        response = SESSION.get(BASE, params={
            "symbol": symbol, "interval": "1h", "endTime": cursor, "limit": 1000,
        }, timeout=25)
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Invalid Binance response for {symbol}: {batch}")
        if not batch:
            break
        now_ms = int(time.time() * 1000)
        valid = [x for x in batch if int(x[6]) < now_ms and int(x[0]) >= begin_ms]
        collected.extend(valid)
        oldest = min(int(x[0]) for x in batch)
        if oldest <= begin_ms:
            break
        cursor = oldest - 1
        time.sleep(0.07)
    if not collected:
        raise RuntimeError(f"No completed klines for {symbol}")
    values = {}
    for x in collected:
        ts = pd.Timestamp(int(x[0]), unit="ms", tz="UTC")
        values[ts] = (float(x[1]), float(x[2]), float(x[3]), float(x[4]))
    frame = pd.DataFrame.from_dict(values, orient="index", columns=["open", "high", "low", "close"])
    frame.index.name = "timestamp"
    return frame.sort_index()


def load_prices():
    by_symbol = {}
    for symbol in SYMBOLS:
        try:
            by_symbol[symbol] = fetch_hourly(symbol)
            print(f"Loaded {symbol}: {len(by_symbol[symbol])} completed hourly bars")
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            print(f"SKIPPED {symbol}: {exc}")
    if "BTCUSDT" not in by_symbol or len(by_symbol) < 4:
        raise RuntimeError("Need BTC and at least 3 additional available symbols")
    # Intersection only: no forward-filled price or look-ahead filling.
    index = by_symbol["BTCUSDT"].index
    for f in by_symbol.values():
        index = index.intersection(f.index)
    index = index.sort_values()
    if len(index) < 600:
        raise RuntimeError("Fewer than 600 synchronized hourly observations")
    fields = {field: pd.DataFrame({s: f.loc[index, field] for s, f in by_symbol.items()}, index=index)
              for field in ("open", "high", "low", "close")}
    if fields["close"].isna().any().any():
        raise RuntimeError("Unexpected missing prices")
    return fields


def make_signals(prices):
    close, high, low = prices["close"], prices["high"], prices["low"]
    universe = [s for s in TRADED if s in close.columns]
    btc = close["BTCUSDT"]
    btc_ok = btc > btc.rolling(48, min_periods=48).mean()
    r24 = close / close.shift(24) - 1
    r72 = close / close.shift(72) - 1
    r168 = close / close.shift(168) - 1

    # Previous N hourly bars' high: shift(1) excludes current candle.
    previous_high24 = high.shift(1).rolling(24, min_periods=24).max()
    previous_high72 = high.shift(1).rolling(72, min_periods=72).max()

    # Volatility contraction: realized volatility in last 24h must be smaller
    # than its trailing 7-day median. Then price breaks above previous 24h high.
    logret = np.log(close / close.shift(1))
    rv24 = logret.rolling(24, min_periods=24).std()
    trailing_rv_median = rv24.shift(1).rolling(168, min_periods=168).median()

    strategies = {}
    # Each signal ranks eligible coins; BTC is a regime filter only.
    strategies["breakout_24h_benchmark"] = (
        (close > previous_high24).where(btc_ok, False), r24)
    strategies["multi_day_breakout_72h"] = (
        (close > previous_high72).where(btc_ok, False), r72)
    strategies["relative_strength_72h"] = (
        ((r72 > r72["BTCUSDT"].values[:, None]) & (r72 > 0)).where(btc_ok, False), r72 - r72["BTCUSDT"].values[:, None])
    strategies["relative_strength_168h"] = (
        ((r168 > r168["BTCUSDT"].values[:, None]) & (r168 > 0)).where(btc_ok, False), r168 - r168["BTCUSDT"].values[:, None])
    strategies["vol_contraction_breakout"] = (
        ((close > previous_high24) & (rv24 < trailing_rv_median)).where(btc_ok, False), r24)

    targets = {}
    for name, (eligibility, rank) in strategies.items():
        weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        for i in range(len(close)):
            # Decisions only at completed bar closes every 6 hours.
            if i < 220 or i % REBALANCE_HOURS != 0:
                if i > 0:
                    weights.iloc[i] = weights.iloc[i - 1]
                continue
            valid = [s for s in universe if bool(eligibility.at[close.index[i], s])
                     and np.isfinite(rank.at[close.index[i], s])]
            winners = sorted(valid, key=lambda s: float(rank.at[close.index[i], s]), reverse=True)[:MAX_POSITIONS]
            if winners:
                weights.loc[close.index[i], winners] = MAX_EXPOSURE / MAX_POSITIONS
        targets[name] = weights
    return targets


def simulate(prices, weights):
    """Weight decided after close[t-1] applies at open[t].

    Approximate open-to-open marking and proportional trading costs; no borrow,
    funding, market impact, liquidity or order-book simulation.
    """
    opening = prices["open"]
    next_open_return = opening.shift(-1) / opening - 1
    desired_at_open = weights.shift(1).fillna(0.0)
    # Rebalance desired weights at each open; execution costs charged on
    # target changes, with drift approximated away between bar opens.
    trades = desired_at_open.diff().abs()
    trades.iloc[0] = desired_at_open.iloc[0].abs()
    traded_fraction = trades.sum(axis=1)
    gross = (desired_at_open * next_open_return).sum(axis=1)
    costs = FEE_AND_SLIPPAGE_PER_SIDE * traded_fraction
    returns = gross - costs
    # Last open cannot be evaluated without the next open.
    returns = returns.iloc[:-1]
    equity = INITIAL_CAPITAL * (1 + returns).cumprod()
    return pd.DataFrame({"return": returns, "equity": equity,
                         "turnover": traded_fraction.loc[returns.index],
                         "cost_fraction": costs.loc[returns.index]})


def metrics(segment):
    r = segment["return"]
    if r.empty:
        return {}
    equity = INITIAL_CAPITAL * (1 + r).cumprod()
    peak = pd.concat([pd.Series([INITIAL_CAPITAL]), equity.reset_index(drop=True)], ignore_index=True).cummax().iloc[1:].to_numpy()
    dd = 1 - equity.to_numpy() / peak
    total = (1 + r).prod() - 1
    periods = len(r)
    ann = (1 + total) ** (365 * 24 / periods) - 1 if total > -1 else -1
    std = r.std(ddof=1)
    downside = np.sqrt(np.mean(np.minimum(r.to_numpy(), 0) ** 2))
    sharpe = np.sqrt(365 * 24) * r.mean() / std if std > 0 else np.nan
    sortino = np.sqrt(365 * 24) * r.mean() / downside if downside > 0 else np.nan
    max_dd = float(np.max(dd))
    return {"net_profit_usd": round(INITIAL_CAPITAL * total, 2),
            "return_pct": round(total * 100, 3),
            "max_drawdown_pct": round(max_dd * 100, 3),
            "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3),
            "calmar": round(ann / max_dd, 3) if max_dd else np.nan,
            "trade_events_approx": int((segment["turnover"] > 0).sum()),
            "total_turnover": round(segment["turnover"].sum(), 3),
            "cost_fraction_sum": round(segment["cost_fraction"].sum(), 4)}


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    prices = load_prices()
    n = len(prices["close"])
    print(f"Synchronized: {n} bars, {len(prices['close'].columns)} symbols")
    print("First candle:", prices["close"].index[0])
    print("Last candle:", prices["close"].index[-1])
    targets = make_signals(prices)
    all_results = {name: simulate(prices, w) for name, w in targets.items()}
    end = min(map(len, all_results.values()))
    # 60% research, 20% validation for selection, 20% untouched final test.
    split1, split2 = int(end * 0.60), int(end * 0.80)
    slices = {"research": slice(0, split1), "validation": slice(split1, split2),
              "final_test": slice(split2, end)}
    records = []
    for name, result in all_results.items():
        result.to_csv(OUTPUT_DIR / f"{name}_hourly.csv")
        for phase, sl in slices.items():
            records.append({"strategy": name, "sample": phase, **metrics(result.iloc[sl])})
    table = pd.DataFrame(records)
    table.to_csv(OUTPUT_DIR / "all_strategy_metrics.csv", index=False)
    validation = table[table["sample"] == "validation"].sort_values("net_profit_usd", ascending=False)
    winner = validation.iloc[0]["strategy"]
    print("\nVALIDATION — RANKED BY NET PROFIT AFTER COSTS")
    print(validation[["strategy", "net_profit_usd", "return_pct", "max_drawdown_pct", "trade_events_approx"]].to_string(index=False))
    final = table[(table["sample"] == "final_test") & (table["strategy"] == winner)]
    print(f"\nSELECTED ON VALIDATION: {winner}")
    print("FINAL TEST — SELECTED STRATEGY ONLY")
    print(final.to_string(index=False))
    print("\nALL FINAL TEST STRATEGIES (DIAGNOSTIC, DO NOT RE-SELECT)")
    print(table[table["sample"] == "final_test"][["strategy", "net_profit_usd", "return_pct", "max_drawdown_pct"]].to_string(index=False))
    for key, frame in prices.items():
        frame.to_csv(OUTPUT_DIR / f"{key}_prices.csv")
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 5))
        for name, result in all_results.items():
            ax.plot(result.index, result["equity"], label=name)
        ax.set_title("Full sample — illustrative strategy portfolio equity")
        ax.set_ylabel("USD")
        ax.legend(fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "equity_curves.png", dpi=150)
        plt.close(fig)
    except ImportError:
        print("matplotlib not installed; chart skipped")
    print(f"\nSaved outputs in: {OUTPUT_DIR.resolve()}")
    print("CAUTION: Binance historical simulation only, not Roostoo performance.")


if __name__ == "__main__":
    main()
