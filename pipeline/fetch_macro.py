import sys
import os
import json
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from loguru import logger
from sqlalchemy import create_engine, text
from tenacity import retry, wait_exponential, stop_after_attempt
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config

load_dotenv(BASE_DIR / ".env")
FRED_API_KEY = os.getenv("FRED_API_KEY")


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def fetch_fred_series(series_id: str) -> pd.Series:
    logger.debug(f"Fetching {series_id} from FRED API...")
    url = f"https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": "2000-01-01"  # Fetch early to ensure ffill works for 2004
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    observations = data.get("observations", [])
    if not observations:
        raise ValueError(f"No observations found for FRED series {series_id}")

    df = pd.DataFrame(observations)
    df = df[df['value'] != '.']
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'])
    df = df.set_index('date')['value']
    df.name = series_id
    logger.info(f"Successfully fetched {len(df)} records for {series_id}")
    return df


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def fetch_yfinance_macro() -> pd.DataFrame:
    logger.debug("Fetching ^VIX and ^GSPC (S&P 500) from yfinance...")
    data = yf.download(["^VIX", "^GSPC"], start="2004-01-01", progress=False)

    # Handle multi-index columns from yf.download
    if isinstance(data.columns, pd.MultiIndex):
        close_df = data['Close']
    else:
        close_df = data

    df = pd.DataFrame({
        'vix': close_df['^VIX'],
        'spy_close': close_df['^GSPC']
    })
    df.index = pd.to_datetime(df.index)
    df = df.dropna()
    logger.info(f"Successfully fetched {len(df)} market records from yfinance")
    return df


def run_macro_pipeline():
    logger.debug("Executing main run_macro_pipeline")

    if not FRED_API_KEY:
        logger.error("Missing FRED_API_KEY in .env. Halting execution.")
        sys.exit(1)

    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    try:
        # 1. Fetch FRED Data
        fed_rate = fetch_fred_series("FEDFUNDS")
        cpi = fetch_fred_series("CPIAUCSL")
        gdp = fetch_fred_series("GDP")
        unrate = fetch_fred_series("UNRATE")

        fred_df = pd.DataFrame({
            'fed_rate': fed_rate,
            'cpi': cpi,
            'gdp_growth': gdp.pct_change() * 100,  # Approximate quarterly growth rate
            'unemployment': unrate
        })

        # 2. Daily Calendar Expansion & Forward Fill
        today = pd.Timestamp.today().normalize()
        daily_idx = pd.date_range(start="2004-01-01", end=today, freq='D')
        fred_daily = fred_df.reindex(daily_idx).ffill()

        # 3. Fetch Market Data & Merge
        yf_df = fetch_yfinance_macro()
        macro_df = yf_df.join(fred_daily, how='left').ffill()

        # 4. Compute SPY EMA & Condition
        macro_df['spy_ema_200'] = macro_df['spy_close'].ewm(span=200, adjust=False).mean()
        macro_df['spy_above_200ema'] = (macro_df['spy_close'] > macro_df['spy_ema_200']).astype(int)

        # Clean up and order columns
        macro_df = macro_df.reset_index().rename(columns={'index': 'date', 'Date': 'date'})
        macro_df['date'] = macro_df['date'].dt.date
        macro_df = macro_df[['date', 'fed_rate', 'cpi', 'gdp_growth', 'unemployment', 'vix', 'spy_close', 'spy_ema_200',
                             'spy_above_200ema']]
        macro_df = macro_df.dropna()

        # 5. Write to DB
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS macro"))
            macro_df.to_sql('macro', con=conn, if_exists='replace', index=False)

            count = conn.execute(text("SELECT COUNT(*) FROM macro")).scalar()
            if count > 5000:
                logger.info(f"SUCCESS: Wrote {count} rows to macro table.")
            else:
                logger.error(f"FAILURE: Expected >5000 rows, got {count}.")

    except Exception as e:
        logger.exception(f"Macro pipeline failed: {e}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    run_macro_pipeline()