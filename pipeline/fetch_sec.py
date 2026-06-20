import sys
import time
import json
import requests
from pathlib import Path
import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy import create_engine

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config

# The SEC strictly requires a descriptive User-Agent or they will shadow-ban your IP.
SEC_HEADERS = {
    "User-Agent": "SignalForge Research (contact@signalforge.app)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "efts.sec.gov"
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
def fetch_ticker_filings(ticker: str) -> list:
    """Queries the SEC EDGAR ElasticSearch API for recent 10-K and 10-Q filings."""
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": ticker,
        "dateRange": "custom",
        "startdt": "2020-01-01",
        "enddt": "2026-12-31",
        "forms": "10-K,10-Q"
    }

    res = requests.get(url, headers=SEC_HEADERS, params=params, timeout=15)
    res.raise_for_status()

    # Extract the raw hit data from the SEC's ElasticSearch response
    hits = res.json().get("hits", {}).get("hits", [])
    return hits


def run_sec_pipeline():
    logger.info("Initializing SEC EDGAR Bulk Ingestion Pipeline...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Get the target universe
    try:
        df_univ = pd.read_sql("SELECT DISTINCT ticker FROM features", engine)
        tickers = df_univ['ticker'].tolist()
    except Exception:
        tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "META"]

    # 2. Ensure storage directories exist
    sec_dir = config.DATA_DIR / "raw" / "sec"
    sec_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Pulling filings for {len(tickers)} tickers. Respecting SEC 10 req/sec limit...")

    success_count = 0
    for i, ticker in enumerate(tickers):
        ticker_dir = sec_dir / ticker
        ticker_dir.mkdir(exist_ok=True)

        try:
            filings = fetch_ticker_filings(ticker)
            if filings:
                # Save the raw JSON response locally
                with open(ticker_dir / "index.json", "w") as f:
                    json.dump(filings, f, indent=4)
                success_count += 1

        except Exception as e:
            logger.debug(f"Failed to fetch SEC index for {ticker}: {e}")

        # 3. Polite SEC throttle (Strictly required by government servers)
        time.sleep(0.15)

        if (i + 1) % 50 == 0:
            logger.info(f"Processed {i + 1}/{len(tickers)} SEC company profiles...")

    logger.success(f"SEC Ingestion Complete. Successfully pulled indexes for {success_count} companies.")


if __name__ == "__main__":
    run_sec_pipeline()