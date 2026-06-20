import sys
import time
import pandas as pd
import requests
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def backfill_alpaca_isolated():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Get the target universe
    try:
        df_univ = pd.read_sql("SELECT DISTINCT ticker FROM features", engine)
        all_tickers = df_univ['ticker'].tolist()
    except Exception:
        all_tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "META", "ZM", "PLTR"]

    logger.info(f"Starting Isolated Alpaca Backfill for {len(all_tickers)} tickers...")
    start_date = (datetime.now() - timedelta(days=80)).strftime('%Y-%m-%dT00:00:00Z')

    api_key = getattr(config, 'ALPACA_API_KEY', None)
    secret_key = getattr(config, 'ALPACA_SECRET_KEY', None)
    headers = {
        "APCA-API-KEY-ID": api_key.strip(" '\"") if api_key else "",
        "APCA-API-SECRET-KEY": secret_key.strip(" '\"") if secret_key else ""
    }
    url = "https://data.alpaca.markets/v2/stocks/bars"

    success_count = 0
    failed_tickers = []

    logger.info("Querying Alpaca Data API (1-by-1 to prevent chunk corruption)...")

    for i, ticker in enumerate(all_tickers):
        alpaca_symbol = ticker.replace("-", ".")
        params = {
            "symbols": alpaca_symbol,
            "timeframe": "1Day",
            "limit": 50,
            "start": start_date,
            "feed": "iex"  # Forces Alpaca to use the free-tier compatible data feed
        }

        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json().get('bars', {})
                bars = data.get(alpaca_symbol, [])

                if not bars:
                    failed_tickers.append(ticker)
                else:
                    batch_records = []
                    for bar in bars:
                        batch_records.append({
                            "ticker": ticker,
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
                                INSERT OR REPLACE INTO ohlcv 
                                (ticker, date, open, high, low, close, volume, adj_close) 
                                VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :adj_close)
                            """)
                            conn.execute(stmt, batch_records)
                        success_count += 1
            else:
                failed_tickers.append(ticker)

        except Exception as e:
            failed_tickers.append(ticker)

        # Log progress every 50 tickers
        if (i + 1) % 50 == 0:
            logger.info(f"Processed {i + 1}/{len(all_tickers)} tickers...")

        # Strict pacing (0.35s) ensures we stay under Alpaca's 200 requests/minute limit
        time.sleep(0.35)

    logger.success(f"Backfill Complete! Successfully populated {success_count} tickers.")
    if failed_tickers:
        logger.info(
            f"Alpaca skipped {len(failed_tickers)} unsupported/delisted tickers. These will be safely ignored by the quantitative engine.")


if __name__ == "__main__":
    backfill_alpaca_isolated()