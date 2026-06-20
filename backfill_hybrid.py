import sys
import time
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def backfill_hybrid():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Get the target universe
    try:
        df_univ = pd.read_sql("SELECT DISTINCT ticker FROM features", engine)
        all_tickers = df_univ['ticker'].tolist()
    except Exception:
        all_tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "META", "ZM", "PLTR"]

    logger.info(f"Starting Hybrid Backfill for {len(all_tickers)} tickers...")
    start_date = (datetime.now() - timedelta(days=80)).strftime('%Y-%m-%dT00:00:00Z')

    # --- PHASE 1: ALPACA BATCH ENGINE ---
    api_key = getattr(config, 'ALPACA_API_KEY', None)
    secret_key = getattr(config, 'ALPACA_SECRET_KEY', None)
    headers = {
        "APCA-API-KEY-ID": api_key.strip(" '\"") if api_key else "",
        "APCA-API-SECRET-KEY": secret_key.strip(" '\"") if secret_key else ""
    }
    url = "https://data.alpaca.markets/v2/stocks/bars"

    alpaca_success = []

    logger.info("PHASE 1: Querying Alpaca Data API...")
    for i in range(0, len(all_tickers), 50):
        chunk = all_tickers[i:i + 50]
        alpaca_chunk = [t.replace("-", ".") for t in chunk]
        params = {"symbols": ",".join(alpaca_chunk), "timeframe": "1Day", "limit": 50, "start": start_date}

        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json().get('bars', {})
                batch_records = []
                for symbol, bars in data.items():
                    db_symbol = symbol.replace(".", "-")
                    alpaca_success.append(db_symbol)
                    for bar in bars:
                        batch_records.append({
                            "ticker": db_symbol, "date": pd.to_datetime(bar['t']).strftime('%Y-%m-%d %H:%M:%S'),
                            "open": float(bar['o']), "high": float(bar['h']), "low": float(bar['l']),
                            "close": float(bar['c']), "volume": float(bar['v']), "adj_close": float(bar['c'])
                        })
                if batch_records:
                    with engine.begin() as conn:
                        stmt = text(
                            "INSERT OR REPLACE INTO ohlcv (ticker, date, open, high, low, close, volume, adj_close) VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :adj_close)")
                        conn.execute(stmt, batch_records)
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Alpaca chunk failed: {e}")

    # --- PHASE 2: YFINANCE FALLBACK ENGINE ---
    starved_tickers = [t for t in all_tickers if t not in alpaca_success]

    if starved_tickers:
        logger.warning(
            f"PHASE 2: Alpaca missed {len(starved_tickers)} tickers (including {starved_tickers[:3]}). Activating YFinance fallback...")

        # Spoof headers to prevent shadow-bans
        session = requests.Session()
        session.headers.update({
                                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})

        for ticker in starved_tickers:
            try:
                # Download last 3 months
                df = yf.download(ticker, period="3mo", interval="1d", session=session, progress=False)
                if df.empty:
                    continue

                # Keep only the last 50 rows
                df = df.tail(50)
                batch_records = []
                for date, row in df.iterrows():
                    batch_records.append({
                        "ticker": ticker, "date": date.strftime('%Y-%m-%d %H:%M:%S'),
                        "open": float(row['Open']), "high": float(row['High']), "low": float(row['Low']),
                        "close": float(row['Close']), "volume": float(row['Volume']), "adj_close": float(row['Close'])
                    })

                if batch_records:
                    with engine.begin() as conn:
                        stmt = text(
                            "INSERT OR REPLACE INTO ohlcv (ticker, date, open, high, low, close, volume, adj_close) VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :adj_close)")
                        conn.execute(stmt, batch_records)
                time.sleep(0.3)  # Polite delay
            except Exception as e:
                logger.error(f"YFinance fallback failed for {ticker}: {e}")

    logger.success("Hybrid backfill complete. All databases are fully armed.")


if __name__ == "__main__":
    backfill_hybrid()