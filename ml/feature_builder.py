import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from loguru import logger

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
import config


def build_features():
    logger.info("Connecting to database...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    logger.info("Loading full OHLCV and News data...")
    ohlcv = pd.read_sql("SELECT * FROM ohlcv", engine)
    ohlcv['date'] = pd.to_datetime(ohlcv['date'], utc=True).dt.normalize()

    news = pd.read_sql("SELECT ticker, date, finbert_sentiment, vader_sentiment FROM news", engine)
    news['date'] = pd.to_datetime(news['date'], utc=True).dt.normalize()

    news_agg = news.groupby(['ticker', 'date']).mean().reset_index()

    logger.info("Merging datasets...")
    df = pd.merge(ohlcv, news_agg, on=['ticker', 'date'], how='left')
    df = df.sort_values(['ticker', 'date'])

    # ==========================================
    # STEP 1 REPAIR: 5-Day Strict Lookback
    # ==========================================
    logger.info("Applying strict 5-day forward-fill to Sentiment...")
    # limit=5 ensures we only remember news for 5 trading days.
    df[['finbert_sentiment', 'vader_sentiment']] = df.groupby('ticker')[
        ['finbert_sentiment', 'vader_sentiment']].ffill(limit=5)

    # If no news within 5 days, sentiment decays to 0 (Neutral)
    df[['finbert_sentiment', 'vader_sentiment']] = df[['finbert_sentiment', 'vader_sentiment']].fillna(0)

    logger.info("Generating Maximum-Edge Quantitative Indicators...")

    # Base Moving Averages
    df['sma_20'] = df.groupby('ticker')['close'].transform(lambda x: x.rolling(20).mean())
    df['sma_50'] = df.groupby('ticker')['close'].transform(lambda x: x.rolling(50).mean())
    df['sma_200'] = df.groupby('ticker')['close'].transform(lambda x: x.rolling(200).mean())

    df['dist_sma_20'] = (df['close'] / df['sma_20']) - 1
    df['dist_sma_50'] = (df['close'] / df['sma_50']) - 1
    df['dist_sma_200'] = (df['close'] / df['sma_200']) - 1

    # RSI (14)
    delta = df.groupby('ticker')['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.groupby(df['ticker']).transform(lambda x: x.rolling(14).mean())
    avg_loss = loss.groupby(df['ticker']).transform(lambda x: x.rolling(14).mean())
    rs = avg_gain / avg_loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = df.groupby('ticker')['close'].transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema_26 = df.groupby('ticker')['close'].transform(lambda x: x.ewm(span=26, adjust=False).mean())
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df.groupby('ticker')['macd'].transform(lambda x: x.ewm(span=9, adjust=False).mean())
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Bollinger Bands (Mean Reversion Edge)
    df['bb_std'] = df.groupby('ticker')['close'].transform(lambda x: x.rolling(20).std())
    df['bb_upper'] = df['sma_20'] + (df['bb_std'] * 2)
    df['bb_lower'] = df['sma_20'] - (df['bb_std'] * 2)
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['sma_20']
    df['bb_percent'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

    # True Range & ATR (Institutional Volatility)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df.groupby('ticker')['close'].shift())
    low_close = np.abs(df['low'] - df.groupby('ticker')['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr_14'] = true_range.groupby(df['ticker']).transform(lambda x: x.rolling(14).mean()) / df['close']

    # Multi-Timeframe Momentum
    df['return_1d'] = df.groupby('ticker')['close'].pct_change(1)
    df['return_5d'] = df.groupby('ticker')['close'].pct_change(5)
    df['return_10d'] = df.groupby('ticker')['close'].pct_change(10)
    df['return_21d'] = df.groupby('ticker')['close'].pct_change(21)

    # Target Generation
    df['next_close'] = df.groupby('ticker')['close'].shift(-1)
    df['target'] = (df['next_close'] > df['close']).astype(int)

    # Target Drop: We cannot train on today if we don't know tomorrow's close
    df = df.dropna(subset=['target'])

    logger.info("Sanitizing Infinity and NaNs (No Data Leaks)...")
    numeric_cols = df.select_dtypes(include=['float64', 'int64', 'float32', 'int32']).columns
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Forward-fill technicals where safe, default to 0 to prevent bfill look-ahead leaks
    df[numeric_cols] = df.groupby('ticker')[numeric_cols].transform(lambda x: x.ffill())
    df = df.fillna(0)

    logger.info("Saving Maximum-Edge Matrix to database...")
    df.to_sql('feature_matrix', engine, if_exists='replace', index=False)
    logger.success(f"Task 10 Complete: Fixed Feature Matrix saved successfully! ({len(df)} rows)")


if __name__ == "__main__":
    build_features()