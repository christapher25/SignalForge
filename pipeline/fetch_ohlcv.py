import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import yfinance as yf
from loguru import logger
from tenacity import retry, wait_exponential, stop_after_attempt
from sqlalchemy import create_engine, text
from tqdm import tqdm

import warnings

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config

# Cache configuration
CACHE_FILE = config.PROCESSED_DIR / "last_fetch.json"


def load_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_cache(cache_data):
    # Ensure directory exists
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache_data, f)


@retry(wait=wait_exponential(multiplier=2, min=5, max=120), stop=stop_after_attempt(5))
def fetch_batch(tickers, start_date):
    """Fetches a batch of tickers. Retries automatically on empty drops or connection resets."""
    # Kept auto_adjust=False to prevent corrupting the math of your 15-year unadjusted training set
    df = yf.download(
        tickers,
        start=start_date,
        group_by='ticker',
        auto_adjust=False,
        threads=False,
        progress=False
    )

    if df is None or df.empty:
        raise ValueError("YF returned empty data. Rate limit likely triggered.")

    return df


def extract_ticker_df(raw_df, ticker):
    """Safely extracts a single ticker's data from yfinance's multi-index dataframe."""
    if isinstance(raw_df.columns, pd.MultiIndex):
        try:
            if ticker in raw_df.columns.levels[0]:
                return raw_df[ticker].dropna(how='all')
            elif ticker in raw_df.columns.levels[1]:
                return raw_df.xs(ticker, level=1, axis=1).dropna(how='all')
        except Exception:
            return pd.DataFrame()
    else:
        # Single ticker batch fallback
        return raw_df.dropna(how='all')
    return pd.DataFrame()


def standardize_yf_df(df, ticker):
    df = df.reset_index()
    rename_map = {
        'Date': 'date', 'Open': 'open', 'High': 'high',
        'Low': 'low', 'Close': 'close', 'Volume': 'volume',
        'Adj Close': 'adj_close'
    }
    df = df.rename(columns=rename_map)
    df.columns = df.columns.str.lower()

    for col in ['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close']:
        if col not in df.columns:
            df[col] = None

    df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close']].copy()
    df['ticker'] = ticker
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df


def run_pipeline():
    config.RAW_DIR.joinpath('ohlcv').mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    universe_files = sorted(list(config.CONSTITUENTS_DIR.glob("sp500_*.json")), reverse=True)
    if not universe_files:
        logger.error("No universe JSON found. Run build_universe.py first.")
        sys.exit(1)

    with open(universe_files[0], 'r') as f:
        tickers = json.load(f)

    fetch_cache = load_cache()
    now = datetime.now()

    # 1. Analyze Delta Requirements & Grouping
    logger.info("Analyzing delta requirements and cache validity...")
    fetch_groups = {}  # { '2026-05-21': ['AAPL', 'MSFT', ...], '2004-01-01': ['NEW_TICKER', ...] }
    up_to_date_count = 0

    for ticker in tickers:
        # Check 6-hour cache layer
        if ticker in fetch_cache:
            last_fetch_time = datetime.fromisoformat(fetch_cache[ticker])
            if now - last_fetch_time < timedelta(hours=6):
                up_to_date_count += 1
                continue

        csv_path = config.RAW_DIR / 'ohlcv' / f"{ticker}.csv"
        start_date = config.START_DATE

        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                if not df.empty:
                    last_date_ts = pd.to_datetime(df['date'].max())
                    today = pd.Timestamp.today().normalize()

                    if last_date_ts >= today:
                        up_to_date_count += 1
                        fetch_cache[ticker] = now.isoformat()
                        continue
                    else:
                        start_date = (last_date_ts + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            except Exception:
                pass  # Corrupt CSV, fallback to full download

        if start_date not in fetch_groups:
            fetch_groups[start_date] = []
        fetch_groups[start_date].append(ticker)

    logger.info(f"{up_to_date_count}/{len(tickers)} tickers are fully updated or cached.")

    # 2. Batch the groups (50 tickers max per request)
    batches = []
    for s_date, t_list in fetch_groups.items():
        for i in range(0, len(t_list), 50):
            batches.append((s_date, t_list[i:i + 50]))

    if not batches:
        logger.info("All OHLCV data is up to date. Exiting.")
        save_cache(fetch_cache)
        return

    logger.info(f"Executing {len(batches)} batched requests...")

    # 3. Download & Process Batches
    for batch_idx, (start_date, batch_tickers) in enumerate(tqdm(batches, desc="Fetching Batches")):
        try:
            raw_df = fetch_batch(batch_tickers, start_date)

            # Process each ticker extracted from the batch
            for ticker in batch_tickers:
                ticker_raw = extract_ticker_df(raw_df, ticker)
                if ticker_raw.empty:
                    continue

                new_df = standardize_yf_df(ticker_raw, ticker)
                csv_path = config.RAW_DIR / 'ohlcv' / f"{ticker}.csv"

                # Append to existing
                if csv_path.exists():
                    existing_df = pd.read_csv(csv_path)
                    existing_df['date'] = pd.to_datetime(existing_df['date']).dt.date
                    combined = pd.concat([existing_df, new_df])
                    combined['date_str'] = combined['date'].astype(str)
                    combined = combined.drop_duplicates(subset=['date_str'], keep='last').drop(columns=['date_str'])
                else:
                    combined = new_df

                # Save CSV
                combined.to_csv(csv_path, index=False)

                # Sync SQLite
                with engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM ohlcv WHERE ticker = '{ticker}'"))
                combined.to_sql('ohlcv', con=engine, if_exists='append', index=False)

                # Update cache timestamp
                fetch_cache[ticker] = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"Batch {batch_idx + 1} failed completely. Error: {e}")

        # Checkpoint Cache every 5 batches to preserve progress if script dies
        if (batch_idx + 1) % 5 == 0:
            save_cache(fetch_cache)

        # Hard sleep between batches to respect YF rate limits
        time.sleep(3)

    # Final cache save
    save_cache(fetch_cache)
    logger.info("OHLCV batched pipeline complete.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    run_pipeline()