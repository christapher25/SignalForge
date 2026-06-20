# check_db_counts.py
import sys
import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def check_counts():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    test_tickers = ["TSLA", "NVDA", "ZM", "PLTR", "META"]

    print("\n--- DATABASE ROW COUNT CHECK (OHLCV TABLE) ---")
    for ticker in test_tickers:
        try:
            query = f"SELECT COUNT(*) as count FROM ohlcv WHERE ticker = '{ticker}'"
            df = pd.read_sql(query, engine)
            count = df['count'].iloc[0]
            print(f"Ticker: {ticker:<6} | Rows found: {count}")
        except Exception as e:
            print(f"Error checking {ticker}: {e}")


if __name__ == "__main__":
    check_counts()