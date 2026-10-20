"""BTC gated momentum. NO ORDER ENDPOINTS.

Input: a long-format CSV with columns timestamp,pair,open,high,low,close;
UTC timestamps; one row per completed hourly candle per pair.
Run: python strategy.py --csv hourly_ohlc.csv
Returns proposed TARGET portfolio weights, not orders.

This adapter deliberately fails closed if BTC reference or enough hourly data
are missing. Binance backtest performance is not evidence for Roostoo tokens.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

MAX_POSITIONS = 3
MAX_EXPOSURE = 0.30
MIN_HISTORY_HOURS = 220


def latest_targets(candles: pd.DataFrame, allowed_pairs, historical=False):
    required = {"timestamp", "pair", "open", "high", "low", "close"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    df = candles.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
    for field in ("open", "high", "low", "close"):
        df[field] = pd.to_numeric(df[field], errors="raise")
    if df[list(("open", "high", "low", "close"))].isna().any().any():
        raise ValueError("Missing OHLC data; refusing signals")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Nonpositive OHLC price")
    if df.duplicated(["timestamp", "pair"]).any():
        raise ValueError("Duplicate pair/timestamp")
    allowed = list(dict.fromkeys(allowed_pairs))
    if not allowed:
        raise ValueError("No tradable pairs configured")
    if "BTC/USD" not in set(df["pair"]):
        raise ValueError("BTC/USD completed-hour reference candles required")
    all_pairs = ["BTC/USD"] + [p for p in allowed if p != "BTC/USD"]
    df = df[df["pair"].isin(all_pairs)]
    close = df.pivot(index="timestamp", columns="pair", values="close").sort_index()
    high = df.pivot(index="timestamp", columns="pair", values="high").reindex(close.index)
    selected_pairs = [p for p in allowed if p in close.columns and p != "BTC/USD"]
    if not selected_pairs:
        raise ValueError("No allowed assets with matching OHLC data")
    close = close[["BTC/USD"] + selected_pairs]
    high = high[close.columns]
    # All markets must have completed candles at precisely the same hourly timestamps.
    if close.isna().any().any() or high.isna().any().any():
        raise ValueError("Missing shared hourly bars")
    idx = close.index
    if len(idx) < MIN_HISTORY_HOURS:
        raise ValueError(f"Need at least {MIN_HISTORY_HOURS} synchronized hourly candles; got {len(idx)}")
    if (idx.to_series().diff().dropna() != pd.Timedelta(hours=1)).any():
        raise ValueError("Hourly data contain gaps or irregular timestamps")
    # The caller must supply completed candles only; do not trust an in-progress bar.
    if not historical:
        if idx[-1] + pd.Timedelta(hours=1) > pd.Timestamp.now(tz="UTC"):
            raise ValueError("Latest hourly candle has not completed")
        if pd.Timestamp.now(tz="UTC") - idx[-1] > pd.Timedelta(hours=2):
            raise ValueError("Last completed candle is stale")
    btc = close["BTC/USD"]
    btc_ok = bool(btc.iloc[-1] > btc.rolling(48, min_periods=48).mean().iloc[-1])
    prev_high = high.shift(1).rolling(24, min_periods=24).max()
    rv24 = np.log(close / close.shift(1)).rolling(24, min_periods=24).std()
    trailing_median = rv24.shift(1).rolling(168, min_periods=168).median()
    r24 = close / close.shift(24) - 1
    chosen = []
    if btc_ok:
        for pair in selected_pairs:
            if (close[pair].iloc[-1] > prev_high[pair].iloc[-1]
                    and rv24[pair].iloc[-1] < trailing_median[pair].iloc[-1]
                    and np.isfinite(r24[pair].iloc[-1])):
                chosen.append((pair, float(r24[pair].iloc[-1])))
    chosen.sort(key=lambda x: x[1], reverse=True)
    chosen = chosen[:MAX_POSITIONS]
    target = {p: 0.0 for p in allowed}
    for pair, _ in chosen:
        target[pair] = MAX_EXPOSURE / MAX_POSITIONS
    return {
        "signal_as_of_completed_candle_utc": idx[-1].isoformat(),
        "btc_uptrend": btc_ok,
        "target_weights": target,
        "ranked_entries": [{"pair": p, "return_24h": r} for p, r in chosen],
        "cash_target_weight": round(1 - sum(target.values()), 10),
        "mode": "SIGNAL_ONLY_NO_TRADES",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Completed hourly OHLC CSV")
    parser.add_argument("--pairs", nargs="+", default=["ETH/USD", "DOGE/USD", "SHIB/USD", "PEPE/USD", "FLOKI/USD", "BONK/USD"])
    args = parser.parse_args()
    candles = pd.read_csv(Path(args.csv))
    result = latest_targets(candles, args.pairs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
