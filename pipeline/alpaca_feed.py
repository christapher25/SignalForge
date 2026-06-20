import sys
import time
import datetime
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from pathlib import Path
from loguru import logger

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def get_active_universe() -> list:
    try:
        engine = create_engine(f"sqlite:///{config.DB_PATH}")
        df = pd.read_sql("SELECT DISTINCT ticker FROM feature_matrix", engine)
        tickers = df['ticker'].tolist()
        return tickers if tickers else ["AAPL", "MSFT", "NVDA", "SPY"]
    except Exception as e:
        logger.error(f"Could not load universe from DB: {e}")
        return ["AAPL", "MSFT", "NVDA", "SPY"]


def chunk_tickers(tickers: list, chunk_size: int = 100):
    for i in range(0, len(tickers), chunk_size):
        yield tickers[i:i + chunk_size]


def poll_market_snapshots():
    logger.info("Initiating universe price snapshot sync...")

    raw_tickers = get_active_universe()
    # FIX 1: Convert YFinance dual-class symbols (BF-B) to Alpaca format (BF.B)
    alpaca_tickers = [t.replace("-", ".") for t in raw_tickers]

    logger.info(f"Loaded {len(alpaca_tickers)} tickers from the tracking directory.")

    api_key = getattr(config, 'ALPACA_API_KEY', None)
    secret_key = getattr(config, 'ALPACA_SECRET_KEY', None)

    if not api_key or not secret_key:
        logger.error("CRITICAL: Alpaca API keys missing in config.py")
        return

    headers = {
        "APCA-API-KEY-ID": api_key.strip(" '\""),
        "APCA-API-SECRET-KEY": secret_key.strip(" '\"")
    }

    url = "https://data.alpaca.markets/v2/stocks/bars/latest"
    batch_records = []
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    for chunk in chunk_tickers(alpaca_tickers, chunk_size=100):
        params = {"symbols": ",".join(chunk)}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                bars_data = response.json().get("bars", {})

                for symbol, bar in bars_data.items():
                    try:
                        raw_time = pd.to_datetime(bar.get("t"))
                        date_str = raw_time.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        date_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # Revert symbol back to YFinance format for DB consistency
                    db_symbol = symbol.replace(".", "-")

                    batch_records.append({
                        "ticker": db_symbol,
                        "date": date_str,
                        "open": float(bar.get("o", 0.0)),
                        "high": float(bar.get("h", 0.0)),
                        "low": float(bar.get("l", 0.0)),
                        "close": float(bar.get("c", 0.0)),
                        "volume": float(bar.get("v", 0.0)),
                        "adj_close": float(bar.get("c", 0.0))
                    })
            else:
                logger.error(f"Alpaca API Error {response.status_code}: {response.text}")

            time.sleep(1.0)
        except Exception as e:
            logger.error(f"Failed to fetch batch chunk: {e}")
            time.sleep(2.0)

    # FIX 2: Safe UPSERT using native SQLite execute instead of pandas to_sql
    if batch_records:
        try:
            with engine.begin() as conn:
                # Using INSERT OR REPLACE allows identical timestamps to overwrite cleanly
                # without triggering the UNIQUE constraint failure.
                stmt = text("""
                    INSERT OR REPLACE INTO ohlcv (ticker, date, open, high, low, close, volume, adj_close) 
                    VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :adj_close)
                """)
                conn.execute(stmt, batch_records)
            logger.success(
                f"Snapshot Complete: Safely merged {len(batch_records)} market records without duplicate conflicts.")
        except Exception as db_err:
            logger.error(f"Database merge failed: {db_err}")
    else:
        logger.warning("Data sync loop finished with no valid market records collected.")


def run_live_feed():
    logger.info("Starting SignalForge REST-Polling Data Feed Daemon...")
    POLL_INTERVAL_SECONDS = 900

    try:
        while True:
            start_time = time.time()
            poll_market_snapshots()
            elapsed = time.time() - start_time
            sleep_duration = max(1.0, POLL_INTERVAL_SECONDS - elapsed)
            logger.info(f"Cycle complete. Entering deep sleep for {int(sleep_duration)} seconds...")
            time.sleep(sleep_duration)
    except KeyboardInterrupt:
        logger.warning("REST-Polling Feed Daemon manually shut down by user.")
    except Exception as e:
        logger.critical(f"Data Feed Daemon encountered a critical crash loop: {e}")


if __name__ == "__main__":
    run_live_feed()