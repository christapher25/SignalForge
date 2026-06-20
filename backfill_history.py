import sys
import pandas as pd
from sqlalchemy import create_engine, text
from loguru import logger
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def backfill_specific_tickers():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # Force backfill specifically for the tickers you are testing
    test_universe = ["TSLA", "NVDA", "ZM", "PLTR", "META"]

    api_key = getattr(config, 'ALPACA_API_KEY', None)
    secret_key = getattr(config, 'ALPACA_SECRET_KEY', None)

    headers = {
        "APCA-API-KEY-ID": api_key.strip(" '\""),
        "APCA-API-SECRET-KEY": secret_key.strip(" '\"")
    }

    logger.info(f"Forcing historical backfill for test universe: {test_universe}")

    start_date = (datetime.now() - timedelta(days=80)).strftime('%Y-%m-%dT00:00:00Z')
    url = "https://data.alpaca.markets/v2/stocks/bars"

    params = {
        "symbols": ",".join(test_universe),
        "timeframe": "1Day",
        "limit": 50,
        "start": start_date,
        "adjustment": "all"
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json().get('bars', {})
            batch_records = []

            for symbol, bars in data.items():
                db_symbol = symbol.replace(".", "-")
                for bar in bars:
                    batch_records.append({
                        "ticker": db_symbol,
                        "date": pd.to_datetime(bar['t']).strftime('%Y-%m-%d %H:%M:%S'),
                        "open": float(bar['o']),
                        "high": float(bar['h']),
                        "low": float(bar['l']),
                        "close": float(bar['c']),
                        "volume": float(bar['v']),
                        "adj_close": float(bar['c'])
                    })

            if batch_records:
                with engine.begin() as conn:
                    stmt = text("""
                        INSERT OR REPLACE INTO ohlcv (ticker, date, open, high, low, close, volume, adj_close) 
                        VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :adj_close)
                    """)
                    conn.execute(stmt, batch_records)
                logger.success(f"Successfully forced {len(batch_records)} historical rows into ohlcv.")
        else:
            logger.error(f"Alpaca API Error: {res.text}")

    except Exception as e:
        logger.error(f"Backfill execution failed: {e}")


if __name__ == "__main__":
    backfill_specific_tickers()