import sys
import json
import asyncio
import aiohttp
import os
import requests
from pathlib import Path
from datetime import date
import pandas as pd
import yfinance as yf
from loguru import logger
from sqlalchemy import create_engine, text
from tqdm.asyncio import tqdm
from tenacity import retry, wait_exponential, stop_after_attempt
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config

# Strict Secret Safety Initialization
load_dotenv(BASE_DIR / ".env")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def get_sec_ciks():
    """Synchronous fetch of SEC CIK mappings."""
    logger.debug("Executing get_sec_ciks()")
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": "SignalForge admin@signalforge.com"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        mapping = {}
        for item in data.values():
            mapping[item['ticker']] = str(item['cik_str']).zfill(10)
        logger.info(f"get_sec_ciks completed: Loaded {len(mapping)} CIK mappings from SEC")
        return mapping
    except Exception as e:
        logger.exception(f"Failed to fetch SEC CIKs: {e}")
        raise


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
async def fetch_macro_newsapi(session):
    """Fetches broad market macro news strictly 5 times per day."""
    logger.debug("Executing fetch_macro_newsapi(session)")

    queries = [
        "S&P 500 earnings",
        "stock market today",
        "Federal Reserve interest rates",
        "nasdaq tech stocks",
        "NYSE market news"
    ]
    all_macro_news = []
    today = date.today()

    for q in queries:
        url = f"https://newsapi.org/v2/everything?q={q}&language=en&sortBy=publishedAt&pageSize=20&apiKey={NEWSAPI_KEY}"
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    for art in data.get('articles', []):
                        dt_str = art.get('publishedAt')
                        dt = pd.to_datetime(dt_str).date() if dt_str else today
                        all_macro_news.append({
                            'ticker': 'MARKET',
                            'date': dt,
                            'headline': art.get('title', ''),
                            'source': art.get('source', {}).get('name', 'NewsAPI'),
                            'full_text': art.get('description') or art.get('title', ''),
                            'finbert_sentiment': None, 'vader_sentiment': None,
                            'sentiment_method': None, 'embedding_id': None
                        })
                else:
                    logger.error(f"NewsAPI macro query '{q}' failed with status {response.status}")
        except Exception as e:
            logger.exception(f"NewsAPI macro query '{q}' threw an exception: {e}")

    logger.info(f"fetch_macro_newsapi completed: Fetched {len(all_macro_news)} market-wide articles")
    return all_macro_news


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def fetch_yfinance_news_sync(ticker):
    """Fetches specific ticker news and synthetic sentiment via YFinance."""
    logger.debug(f"Executing fetch_yfinance_news_sync(ticker={ticker})")
    res = []
    try:
        tk = yf.Ticker(ticker)

        # 1. Structured Headlines via get_news() or news
        news = tk.get_news() if hasattr(tk, 'get_news') else tk.news
        if isinstance(news, list):
            for art in news:
                if 'title' in art and 'providerPublishTime' in art:
                    dt = pd.to_datetime(art['providerPublishTime'], unit='s').date()
                    res.append({
                        'ticker': ticker, 'date': dt, 'headline': art['title'],
                        'source': art.get('publisher', 'Yahoo Finance'),
                        'full_text': art.get('summary', art['title']),
                        'finbert_sentiment': None, 'vader_sentiment': None,
                        'sentiment_method': None, 'embedding_id': None
                    })

        # 2. Synthetic Sentiment from Earnings Surprises
        hist = tk.earnings_dates if hasattr(tk, 'earnings_dates') else tk.earnings_history
        if hist is not None and not hist.empty:
            hist = hist.reset_index()
            for _, row in hist.iterrows():
                surprise_col = 'Surprise(%)' if 'Surprise(%)' in hist.columns else 'surprisePercent'
                date_col = 'Earnings Date' if 'Earnings Date' in hist.columns else 'epsActualDate'
                if surprise_col in row and pd.notna(row[surprise_col]):
                    surprise = float(row[surprise_col])
                    dt = pd.to_datetime(row[date_col]).date() if date_col in row else None
                    if dt:
                        sentiment = 1.0 if surprise > 0 else -1.0 if surprise < 0 else 0.0
                        res.append({
                            'ticker': ticker, 'date': dt,
                            'headline': f"{ticker} Earnings Surprise: {surprise:.2f}%",
                            'source': 'Synthetic_Earnings', 'full_text': f"Earnings surprise of {surprise:.2f}%",
                            'finbert_sentiment': None, 'vader_sentiment': sentiment,
                            'sentiment_method': 'vader', 'embedding_id': None
                        })

        # 3. Synthetic Sentiment from Analyst Recommendations
        recs = tk.upgrades_downgrades if hasattr(tk, 'upgrades_downgrades') else tk.recommendations
        if recs is not None and not recs.empty:
            recs = recs.reset_index()
            for _, row in recs.iterrows():
                action_col = 'Action' if 'Action' in recs.columns else 'To Grade'
                date_col = 'Grade Date' if 'Grade Date' in recs.columns else 'Date'
                if action_col in row and date_col in row:
                    action = str(row[action_col]).lower()
                    dt = pd.to_datetime(row[date_col]).date()
                    sentiment = 0.5 if action in ['up', 'buy', 'outperform'] else -0.5 if action in ['down', 'sell',
                                                                                                     'underperform'] else 0.0
                    res.append({
                        'ticker': ticker, 'date': dt,
                        'headline': f"{ticker} Analyst Action: {action.title()}",
                        'source': 'Synthetic_Analyst', 'full_text': f"Firm action: {action}",
                        'finbert_sentiment': None, 'vader_sentiment': sentiment,
                        'sentiment_method': 'vader', 'embedding_id': None
                    })
    except Exception as e:
        logger.exception(f"fetch_yfinance_news_sync failed for {ticker}: {e}")

    logger.info(f"fetch_yfinance_news_sync completed: Extracted {len(res)} events for {ticker}")
    return res


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
async def fetch_sec_edgar(session, ticker, cik):
    """Fetches SEC EDGAR company facts to generate synthetic earnings news."""
    if not cik:
        logger.debug(f"Executing fetch_sec_edgar(ticker={ticker}) - NO CIK AVAILABLE")
        return []

    logger.debug(f"Executing fetch_sec_edgar(ticker={ticker}, cik={cik})")
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    headers = {"User-Agent": "SignalForge admin@signalforge.com"}
    res_data = []

    try:
        async with session.get(url, headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.error(f"SEC EDGAR returned status {response.status} for {ticker}")
                return []
            data = await response.json()
            usd_facts = data.get('facts', {}).get('us-gaap', {}).get('NetIncomeLoss', {}).get('units', {}).get('USD',
                                                                                                               [])

            if not usd_facts:
                return []

            df = pd.DataFrame(usd_facts)
            if 'end' not in df.columns or 'val' not in df.columns:
                return []

            df = df.sort_values('end').drop_duplicates(subset=['end'], keep='last')
            df['val'] = pd.to_numeric(df['val'], errors='coerce')
            df['pct_change'] = df['val'].pct_change()

            for _, row in df.iterrows():
                if pd.notna(row['pct_change']) and abs(row['pct_change']) >= 0.10:
                    dt = pd.to_datetime(row['end']).date()
                    val_m = row['val'] / 1e6
                    pct_str = f"{row['pct_change'] * 100:+.1f}%"
                    res_data.append({
                        'ticker': ticker, 'date': dt,
                        'headline': f"{ticker} reports quarterly earnings: ${val_m:.1f}M ({pct_str} vs prior quarter)",
                        'source': 'SEC EDGAR', 'full_text': "Net Income Loss change threshold triggered.",
                        'finbert_sentiment': None, 'vader_sentiment': None,
                        'sentiment_method': None, 'embedding_id': None
                    })
    except Exception as e:
        logger.exception(f"fetch_sec_edgar failed for {ticker}: {e}")

    logger.info(f"fetch_sec_edgar completed: Extracted {len(res_data)} synthetic events for {ticker}")
    return res_data


async def process_ticker(ticker, cik, session, sem):
    """Processes an individual ticker concurrently."""
    logger.debug(f"Executing process_ticker(ticker={ticker})")
    async with sem:
        news = []
        news.extend(await fetch_sec_edgar(session, ticker, cik))
        news.extend(await asyncio.to_thread(fetch_yfinance_news_sync, ticker))
        logger.info(f"process_ticker completed for {ticker} with {len(news)} items.")
        return news


async def main():
    """Main execution pipeline."""
    logger.debug("Executing main()")

    # 1. Strict Secret Check
    if not NEWSAPI_KEY:
        logger.error("Missing NEWSAPI_KEY in .env. Halting execution.")
        sys.exit(1)

    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = config.PROCESSED_DIR / 'news_checkpoint.json'

    universe_files = sorted(list(config.CONSTITUENTS_DIR.glob("sp500_*.json")), reverse=True)
    with open(universe_files[0], 'r') as f:
        all_tickers = json.load(f)

    valid_tickers = [t for t in all_tickers if len(t) > 1]
    cik_map = get_sec_ciks()

    processed_tickers = set()
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, 'r') as f:
                processed_tickers = set(json.load(f))
            logger.info(f"Loaded checkpoint: {len(processed_tickers)} tickers already processed.")
        except Exception as e:
            logger.exception(f"Failed to load checkpoint file: {e}")

    pending_tickers = [t for t in valid_tickers if t not in processed_tickers]
    logger.info(f"Starting news processing for {len(pending_tickers)} pending tickers.")

    sem = asyncio.Semaphore(5)

    async with aiohttp.ClientSession() as session:
        # 2. Daily Macro News Fetch (Run Once)
        try:
            with engine.begin() as conn:
                today_str = date.today().isoformat()
                existing_macro = conn.execute(
                    text(f"SELECT COUNT(*) FROM news WHERE ticker='MARKET' AND date='{today_str}'")).scalar()

            if existing_macro == 0:
                logger.info("Fetching daily macro news batch from NewsAPI...")
                macro_news = await fetch_macro_newsapi(session)
                if macro_news:
                    df_macro = pd.DataFrame(macro_news).dropna(subset=['date', 'headline'])
                    df_macro.drop_duplicates(subset=['ticker', 'headline'], inplace=True)

                    try:
                        with engine.begin() as conn:
                            b_count = conn.execute(text("SELECT COUNT(*) FROM news")).scalar()
                            df_macro.to_sql('news', con=conn, if_exists='append', index=False)
                            a_count = conn.execute(text("SELECT COUNT(*) FROM news")).scalar()

                            if a_count <= b_count and len(df_macro) > 0:
                                logger.error("Database write silently failed for macro news.")
                            else:
                                logger.info(f"Successfully wrote {a_count - b_count} macro news rows to DB.")
                    except Exception as e:
                        logger.exception(f"Database transaction failed for macro news: {e}")
            else:
                logger.info("Daily macro news already exists in database. Skipping.")
        except Exception as e:
            logger.exception(f"Failed checking/inserting macro news: {e}")

        # 3. Ticker Batch Processing
        for i in tqdm(range(0, len(pending_tickers), 50), desc="Processing Batches"):
            batch = pending_tickers[i:i + 50]

            tasks = []
            for t in batch:
                cik = cik_map.get(t)
                tasks.append(process_ticker(t, cik, session, sem))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_news = []
            successful_tickers = []

            for t, res in zip(batch, results):
                if isinstance(res, Exception):
                    logger.error(f"Error processing {t}: {res}")
                else:
                    batch_news.extend(res)
                    successful_tickers.append(t)

            if batch_news:
                df = pd.DataFrame(batch_news).dropna(subset=['date', 'headline'])
                df.drop_duplicates(subset=['ticker', 'headline'], inplace=True)

                # Transactional database write with validation
                try:
                    with engine.begin() as conn:
                        before_count = conn.execute(text("SELECT COUNT(*) FROM news")).scalar()
                        df.to_sql('news', con=conn, if_exists='append', index=False)
                        after_count = conn.execute(text("SELECT COUNT(*) FROM news")).scalar()

                        if after_count <= before_count and len(df) > 0:
                            logger.error(f"Database write silently failed for batch {i}.")
                        else:
                            logger.info(f"Successfully wrote {after_count - before_count} rows to DB.")
                except Exception as e:
                    logger.exception(f"Database transaction failed for batch {i}: {e}")

            processed_tickers.update(successful_tickers)
            try:
                with open(checkpoint_file, 'w') as f:
                    json.dump(list(processed_tickers), f)
            except Exception as e:
                logger.exception(f"Failed to write checkpoint file: {e}")

    logger.info("main() completed: News ingestion pipeline finished.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())