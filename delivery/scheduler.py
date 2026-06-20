import sys
import time
import datetime
import requests
from typing import Dict, Any, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from ml.outcome_recorder import record_outcomes
from ml.incremental_retrain import incremental_retrain

import pandas as pd
import torch
import schedule
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from signals.signal_generator import generate_signal
from delivery.channel_manager import broadcast_signals

# --- GLOBAL MEMORY FOR OVERNIGHT LOOP FIX ---
_SENT_TODAY = set()
_LAST_RESET_DATE = datetime.date.today()


# ==========================================
# PART 1: CORE QUANTITATIVE MARKET SCANNER
# ==========================================

def get_active_universe() -> List[str]:
    """Fetches the list of active tickers from the local database."""
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    try:
        with Session(engine) as session:
            result = session.execute(text("SELECT DISTINCT ticker FROM features"))
            tickers = [row[0] for row in result.fetchall()]
        return tickers if tickers else ['AAPL', 'MSFT', 'NVDA']
    except Exception as e:
        logger.error(f"Failed to fetch universe from DB: {e}")
        return ['AAPL', 'MSFT', 'NVDA']


def get_latest_sentiment(ticker: str, engine) -> float:
    """Fetches the most recent live FinBERT score for a ticker to use as a veto."""
    try:
        query = text("""
            SELECT finbert_sentiment 
            FROM news 
            WHERE ticker = :ticker 
            ORDER BY date DESC, rowid DESC LIMIT 1
        """)
        with Session(engine) as session:
            result = session.execute(query, {"ticker": ticker}).scalar()
            return float(result) if result is not None else 0.0
    except Exception as e:
        logger.debug(f"Sentiment fetch failed for {ticker}, defaulting to Neutral: {e}")
        return 0.0


def run_market_scan(mode: str = "INTRADAY") -> None:
    """
    The core trading engine. Scans the universe, respects dynamic thresholds,
    applies the Live NLP Veto, and routes signals to the correct channels.
    """
    global _SENT_TODAY, _LAST_RESET_DATE

    if datetime.date.today() != _LAST_RESET_DATE:
        _SENT_TODAY.clear()
        _LAST_RESET_DATE = datetime.date.today()

    logger.info(f"Starting {mode} decoupled quantitative scan across universe...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    tickers = get_active_universe()

    buy_candidates: List[Dict[str, Any]] = []
    sell_candidates: List[Dict[str, Any]] = []

    STRONG_NEGATIVE_NEWS = -0.30
    STRONG_POSITIVE_NEWS = 0.30

    for ticker in tickers:
        if ticker in _SENT_TODAY:
            continue

        try:
            sig = generate_signal(ticker, mode)
            if not sig:
                continue

            action = sig.get('action')

            if action in ["BUY", "SELL"]:
                live_sentiment = get_latest_sentiment(ticker, engine)

                if action == "BUY" and live_sentiment <= STRONG_NEGATIVE_NEWS:
                    logger.warning(f"VETOED BUY on {ticker}: Strong Negative Live News ({live_sentiment:.2f})")
                    continue

                if action == "SELL" and live_sentiment >= STRONG_POSITIVE_NEWS:
                    logger.warning(f"VETOED SELL on {ticker}: Strong Positive Live News ({live_sentiment:.2f})")
                    continue

                if action == "BUY":
                    buy_candidates.append(sig)
                elif action == "SELL":
                    sell_candidates.append(sig)

        except Exception as e:
            logger.error(f"Skipping scan for {ticker} due to processing error: {e}")

    buy_candidates = sorted(buy_candidates, key=lambda x: x.get('confidence', 0), reverse=True)
    sell_candidates = sorted(sell_candidates, key=lambda x: x.get('confidence', 0), reverse=True)

    buys = buy_candidates[:3]
    sells = sell_candidates[:2]
    pro_signals = buys + sells

    if not pro_signals:
        logger.warning("Scan finished: No assets crossed the required independent alpha thresholds.")
        return

    for sig in pro_signals:
        _SENT_TODAY.add(sig['ticker'])

    tz_et = datetime.timezone(datetime.timedelta(hours=-5))
    scan_time_str = datetime.datetime.now(tz_et).strftime("%I:%M%p").lstrip("0")

    logger.info(f"Dispatching {len(pro_signals)} signals to the Channel Manager...")
    broadcast_signals(pro_signals, scan_time_str)


# ==========================================
# PART 2: INSTITUTIONAL NEWS INGESTION
# ==========================================

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
def fetch_ticker_news(ticker: str) -> List[Dict[str, Any]]:
    """
    Fetches institutional news via Alpaca Data API, falling back to NewsAPI.
    Returns standard database-ready dictionaries.
    """
    articles = []

    # Strictly respect Alpaca's 200 req/minute rate limit (delay 1 second per worker)
    time.sleep(1.0)

    # 1. Primary Engine: ALPACA REST API
    alpaca_key = getattr(config, 'ALPACA_API_KEY', None)
    alpaca_sec = getattr(config, 'ALPACA_SECRET_KEY', None)

    if alpaca_key and alpaca_sec:
        url = f"https://data.alpaca.markets/v1beta1/news?symbols={ticker}&limit=3"
        headers = {
            "APCA-API-KEY-ID": alpaca_key,
            "APCA-API-SECRET-KEY": alpaca_sec
        }
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json().get('news', [])
                for item in data:
                    headline = item.get('headline', '') or ''
                    summary = item.get('summary', '') or headline
                    pub_date = pd.to_datetime(item.get('created_at')).date()
                    url_uuid = str(item.get('id', item.get('url', f"alpaca_{ticker}_{pub_date}")))

                    articles.append({
                        "ticker": ticker,
                        "date": pub_date,
                        "headline": headline,
                        "source": item.get('source', 'Alpaca'),
                        "full_text": summary,
                        "uuid": url_uuid
                    })
        except Exception as e:
            logger.debug(f"Alpaca API failed for {ticker}: {e}")

    # 2. If Alpaca finds nothing, Fallback to NewsAPI
    newsapi_key = getattr(config, 'NEWSAPI_KEY', None)

    if not articles and newsapi_key:
        url = f"https://newsapi.org/v2/everything?q={ticker} stock&language=en&sortBy=publishedAt&pageSize=2"
        headers = {"X-Api-Key": newsapi_key}
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json().get('articles', [])
                for item in data:
                    headline = item.get('title', '') or ''
                    summary = item.get('description', '') or headline
                    pub_date = pd.to_datetime(item.get('publishedAt')).date()
                    url_uuid = str(item.get('url', f"newsapi_{ticker}_{pub_date}"))

                    articles.append({
                        "ticker": ticker,
                        "date": pub_date,
                        "headline": headline,
                        "source": item.get('source', {}).get('name', 'NewsAPI'),
                        "full_text": summary,
                        "uuid": url_uuid
                    })
        except Exception as e:
            logger.debug(f"NewsAPI failed for {ticker}: {e}")

    return articles


def run_live_news_refresh() -> None:
    """Scans universe using safe concurrency and FinBERT via official APIs."""
    logger.info("Initializing Institutional Market News Refresh Loop...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    all_tickers = get_active_universe()
    raw_articles = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_ticker = {executor.submit(fetch_ticker_news, t): t for t in all_tickers}

        count = 0
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                news_items = future.result()
                if news_items:
                    raw_articles.extend(news_items)
            except Exception as e:
                logger.error(f"News fetch failed for {ticker}: {e}")

            count += 1
            if count % 50 == 0:
                logger.info(f"Processed news APIs for {count}/{len(all_tickers)} tickers...")

    if not raw_articles:
        logger.warning("No articles fetched from APIs during this cycle.")
        return

    # --- SQLITE LIMIT FIX: Chunk Database Reads ---
    new_articles = []
    try:
        with Session(engine) as session:
            # Extract unique UUIDs from the fetched batch
            all_uuids = list({str(a["uuid"]) for a in raw_articles})
            existing_uuids = set()

            if all_uuids:
                # Process in chunks of 500 to avoid SQLite limits
                chunk_size = 500
                for i in range(0, len(all_uuids), chunk_size):
                    chunk = all_uuids[i:i + chunk_size]

                    # Dynamically build bound parameters for the IN clause
                    placeholders = ", ".join([f":id_{j}" for j in range(len(chunk))])
                    query = text(f"SELECT uuid FROM news WHERE uuid IN ({placeholders})")

                    # Map the actual values
                    params = {f"id_{j}": uuid for j, uuid in enumerate(chunk)}

                    result = session.execute(query, params)
                    existing_uuids.update(row[0] for row in result.fetchall())

            # Filter out the existing ones
            for article in raw_articles:
                if article["uuid"] not in existing_uuids:
                    new_articles.append(article)
                    existing_uuids.add(article["uuid"])  # Prevent duplicates within the same batch

    except Exception as e:
        logger.error(f"Database UUID duplicate verification failed: {e}")
        return

    already_existed = len(raw_articles) - len(new_articles)
    if not new_articles:
        logger.info(f"News refresh complete: 0 new articles ingested, {already_existed} already existed.")
        return

    logger.info(f"Found {len(new_articles)} new breaking articles. Booting FinBERT processing cluster...")

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert").to(device)
        model.eval()

        texts = [article["full_text"][:512] for article in new_articles]
        batch_size = 32
        sentiment_scores = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i: i + batch_size]
            inputs = tokenizer(batch_texts, return_tensors="pt", padding=True, truncation=True, max_length=512).to(
                device)

            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                batch_scores = (probs[:, 0] - probs[:, 1]).cpu().numpy()
                sentiment_scores.extend(batch_scores)

        for idx, article in enumerate(new_articles):
            article["finbert_sentiment"] = float(sentiment_scores[idx])
            article["sentiment_method"] = "finbert_live"

    except Exception as e:
        logger.error(f"FinBERT cluster inference crashed: {e}")
        return

    try:
        with Session(engine) as session:
            insert_stmt = text("""
                INSERT INTO news (ticker, date, headline, source, full_text, finbert_sentiment, sentiment_method, uuid)
                VALUES (:ticker, :date, :headline, :source, :full_text, :finbert_sentiment, :sentiment_method, :uuid)
            """)
            session.execute(insert_stmt, new_articles)
            session.commit()
        logger.success(
            f"News refresh complete: {len(new_articles)} new articles ingested, {already_existed} already existed.")
    except Exception as e:
        logger.error(f"Failed to write new scored articles to database: {e}")


# ==========================================
# PART 3: THE LIVE INFINITE CLOCK
# ==========================================

if __name__ == "__main__":
    logger.info("Starting SignalForge Live Delivery Scheduler...")

    # 1. --- FORCE IMMEDIATE EXECUTION ON BOOT FIRST ---
    logger.info("Bootstrapping: Running initial API news ingest and market scan immediately...")
    run_live_news_refresh()
    run_market_scan(mode="INTRADAY")

    # 2. --- REGISTER BACKGROUND SCHEDULES AFTER BOOT COMPLETE ---
    schedule.every(30).minutes.do(run_market_scan, mode="INTRADAY")
    schedule.every(2).hours.do(run_live_news_refresh)

    # --- The Daily Learning Loop ---
    # Grades your signals every day so you can track your win rate
    schedule.every().day.at("16:15").do(record_outcomes)

    # FROZEN FOR V1 LAUNCH: Prevents the model from rewriting its own brain
    # schedule.every().day.at("23:00").do(incremental_retrain)
    # -----------------------------------------

    logger.info("Scheduler Armed. Waiting for subsequent market intervals...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Scheduler manually stopped.")