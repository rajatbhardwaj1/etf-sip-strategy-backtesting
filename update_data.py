"""
Incrementally append fresh OHLCV rows to the CSVs in data/.

For every data/<SYMBOL>.csv it reads the last stored date, downloads from that
date to today with yfinance and appends only the genuinely new rows, keeping the
existing two-row header layout (Date,Close,High,Low,Open,Volume + ticker row).
"""
import os
import sys
import time

import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
COLUMNS = ["Close", "High", "Low", "Open", "Volume"]


def last_date(path: str):
    df = pd.read_csv(path, usecols=["Date"], parse_dates=["Date"])
    df = df.dropna(subset=["Date"])
    return None if df.empty else df["Date"].max()


def fetch(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        return pd.DataFrame()
    return df[["Date"] + COLUMNS]


def create(path: str, symbol: str, end: pd.Timestamp, start: str = "2015-01-01") -> int:
    """Download a symbol we have never stored before, in the same two-row header layout."""
    new = fetch(symbol, pd.Timestamp(start), end + pd.Timedelta(days=1))
    if new.empty:
        print(f"{symbol}: nothing returned, not created")
        return 0
    new = new.dropna(subset=["Close"]).sort_values("Date")
    with open(path, "w") as fh:
        fh.write("Date," + ",".join(COLUMNS) + "\n")
        fh.write("," + ",".join([symbol] * len(COLUMNS)) + "\n")
        out = new.copy()
        out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
        out.to_csv(fh, header=False, index=False)
    print(f"{symbol}: created with {len(new)} rows ({new['Date'].min().date()} -> {new['Date'].max().date()})")
    return len(new)


def update(path: str, symbol: str, end: pd.Timestamp) -> int:
    start = last_date(path)
    if start is None:
        print(f"{symbol}: no existing dates, skipped")
        return 0
    new = fetch(symbol, start, end + pd.Timedelta(days=1))
    if new.empty:
        print(f"{symbol}: nothing returned")
        return 0
    new = new[new["Date"] > start].sort_values("Date")
    new = new.dropna(subset=["Close"])
    if new.empty:
        print(f"{symbol}: already up to date ({start.date()})")
        return 0
    rows = new.copy()
    rows["Date"] = rows["Date"].dt.strftime("%Y-%m-%d")
    with open(path, "a") as fh:
        rows.to_csv(fh, header=False, index=False)
    print(f"{symbol}: +{len(rows)} rows ({new['Date'].min().date()} -> {new['Date'].max().date()})")
    return len(rows)


def main():
    end = pd.Timestamp.today().normalize()
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".csv"))
    if len(sys.argv) > 1:
        # Named symbols we have never stored are downloaded from scratch.
        wanted = [a if a.endswith(".csv") else f"{a}.csv" for a in sys.argv[1:]]
        files = [f for f in wanted if f in files]
        missing = [f for f in wanted if f not in files]
    else:
        missing = []
    total = 0
    for fname in missing:
        symbol = fname[:-4]
        try:
            total += create(os.path.join(DATA_DIR, fname), symbol, end)
        except Exception as exc:
            print(f"{symbol}: FAILED ({exc})")
        time.sleep(0.4)
    for fname in files:
        symbol = fname[:-4]
        try:
            total += update(os.path.join(DATA_DIR, fname), symbol, end)
        except Exception as exc:
            print(f"{symbol}: FAILED ({exc})")
        time.sleep(0.4)
    files = files + missing
    print(f"\nDone. {total} new rows across {len(files)} files. Data now through {end.date()}.")


if __name__ == "__main__":
    main()
