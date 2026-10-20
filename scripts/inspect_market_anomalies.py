"""
Inspect Market Data Anomalies.
"""

from pathlib import Path
import pandas as pd

p = Path("data/processed/market/sp500_market_sample.parquet")
if p.exists():
    df = pd.read_parquet(p)
    bad = df[(df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)]
    print("Anomalous rows by ticker:")
    print(bad["ticker"].value_counts())
    print("\nSample rows:")
    print(bad[["ticker", "trading_date", "open", "high", "low", "close", "volume"]].head(10))
