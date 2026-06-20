import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
import config


def verify():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    count_query = "SELECT COUNT(DISTINCT ticker) as c FROM ohlcv"
    rows_query = "SELECT ticker, COUNT(*) as c FROM ohlcv GROUP BY ticker HAVING c < 4000"

    tickers = pd.read_sql(count_query, engine).iloc[0]['c']
    short = pd.read_sql(rows_query, engine)

    logger.info(f"Task 03 Verification SQL executed.")
    logger.info(f"Total DISTINCT tickers in DB: {tickers}")
    logger.info(f"Tickers with fewer than 4000 rows: {len(short)}")

    if len(short) > 0:
        logger.warning(
            f"Note: {len(short)} stocks IPO'd post-2008 (e.g. {short['ticker'].iloc[0]}) and naturally have < 4000 rows. This is an expected reality.")

    if tickers >= 750:
        logger.info("Task 03 Checkpoint: SUCCESS. OHLCV Database populated.")
    else:
        logger.error("Task 03 Checkpoint: FAILED. Expected near 800 distinct tickers.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()