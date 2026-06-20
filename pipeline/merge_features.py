import sys
import warnings
from pathlib import Path
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config

def run_feature_merge():
    logger.info("Starting master feature merge & absolute value purge...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Load Data
    df_ohlcv = pd.read_sql("SELECT ticker, date, close FROM ohlcv", engine)
    df_ind = pd.read_sql("SELECT * FROM indicators", engine)
    df_macro = pd.read_sql("SELECT * FROM macro", engine)
    df_news = pd.read_sql("SELECT ticker, date, AVG(vader_sentiment) as vader, AVG(finbert_sentiment) as finbert FROM news GROUP BY ticker, date", engine)

    # Align dates
    for df in [df_ohlcv, df_ind, df_macro, df_news]:
        if not df.empty:
            df['date'] = pd.to_datetime(df['date']).dt.date

    # 2. Master Merge
    df_merged = pd.merge(df_ind, df_ohlcv, on=['ticker', 'date'], how='left')
    df_merged = pd.merge(df_merged, df_macro, on='date', how='left')
    df_merged = pd.merge(df_merged, df_news, on=['ticker', 'date'], how='left')

    df_merged = df_merged.sort_values(['ticker', 'date'])

    # 3. Clean Sentiment (Forward fill, then 0 for true missing)
    df_merged['vader'] = df_merged.groupby('ticker')['vader'].ffill().fillna(0.0)
    df_merged['finbert'] = df_merged.groupby('ticker')['finbert'].ffill().fillna(0.0)

    # 4. Normalize Macro
    df_merged['spy_dist'] = (df_merged['spy_close'] / df_merged['spy_ema_200']) - 1

    # 5. Generate Target (Strict binary: 1 if next day closes higher, 0 if lower)
    df_merged['target'] = (df_merged.groupby('ticker')['close'].shift(-1) > df_merged['close']).astype(int)

    # 6. THE PURGE: Destroy all absolute price/volume columns
    drop_cols = ['close', 'spy_close', 'spy_ema_200', 'spy_above_200ema']
    df_merged = df_merged.drop(columns=[c for c in drop_cols if c in df_merged.columns])

    # Final cleanup of any lingering NaNs from rolling windows
    df_merged = df_merged.dropna()

    # 7. Write cleanly to database
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS features"))
        df_merged.to_sql('features', con=conn, index=False)

    logger.success(f"Feature engineering complete. {len(df_merged)} timeless vectors saved.")

if __name__ == "__main__":
    run_feature_merge()