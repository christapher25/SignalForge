import sys
from pathlib import Path
import requests
import yfinance as yf
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
import config


def fetch_breaking_news(ticker: str):
    """
    Surgically fetches breaking news for a single ticker.
    Tries NewsAPI first (limit 100/day). Falls back to YFinance.
    """
    articles = []
    today = pd.Timestamp.now().strftime('%Y-%m-%d')

    # 1. Try NewsAPI (High quality, but strictly rate-limited)
    if config.NEWSAPI_KEY:
        url = f"https://newsapi.org/v2/everything?q={ticker}&language=en&sortBy=publishedAt&apiKey={config.NEWSAPI_KEY}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json().get('articles', [])
                for a in data[:5]:  # Top 5 breaking headlines
                    articles.append({
                        'ticker': ticker, 'date': today,
                        'headline': a['title'], 'source': 'NewsAPI',
                        'full_text': a.get('description', ''),
                        'sentiment_method': 'pending'
                    })
                logger.info(f"Pulled {len(articles)} breaking articles from NewsAPI for {ticker}")
                return articles
        except Exception as e:
            logger.warning(f"NewsAPI failed for {ticker}: {e}. Falling back to YFinance.")

    # 2. Fallback to Yahoo Finance (Unlimited)
    try:
        tkr = yf.Ticker(ticker)
        news = tkr.news
        for n in news[:5]:
            articles.append({
                'ticker': ticker, 'date': today,
                'headline': n['title'], 'source': 'YFinance',
                'full_text': n.get('publisher', ''),
                'sentiment_method': 'pending'
            })
        logger.info(f"Pulled {len(articles)} breaking articles from YFinance for {ticker}")
    except Exception as e:
        logger.error(f"YFinance news fetch failed for {ticker}: {e}")

    return articles


def save_live_news(ticker: str):
    """Fetches breaking news and saves to DB for the sentiment engine."""
    articles = fetch_breaking_news(ticker)
    if not articles:
        return

    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    df = pd.DataFrame(articles)
    df.to_sql('news', engine, if_exists='append', index=False)


if __name__ == "__main__":
    # Quick Test
    logger.add(sys.stdout, format="{message}")
    save_live_news("AAPL")