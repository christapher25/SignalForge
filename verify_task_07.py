import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
import config


def verify():
    logger.debug("Executing Task 07 Verification")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    try:
        query = text("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT ticker) as unique_tickers,
            SUM(CASE WHEN finbert_sentiment IS NULL THEN 1 ELSE 0 END) as null_sentiment,
            SUM(CASE WHEN target_1d IS NULL THEN 1 ELSE 0 END) as null_targets
        FROM features
        """)

        with engine.connect() as conn:
            stats = pd.read_sql(query, conn).iloc[0]

        logger.info("Task 07 Verification SQL executed.")
        logger.info(f"Total Master Rows: {int(stats['total_rows'])}")
        logger.info(f"Unique Tickers: {int(stats['unique_tickers'])}")

        if stats['total_rows'] > 1000000 and stats['unique_tickers'] >= 750:
            logger.info("Task 07 Checkpoint: SUCCESS. Master features table is fully assembled and ML-ready.")

            # The most recent dates naturally have NULL forward targets, so > 0 is expected, but shouldn't equal total rows.
            target_null_ratio = stats['null_targets'] / stats['total_rows']
            if target_null_ratio > 0.05:
                logger.warning(
                    f"High number of NULL targets detected ({target_null_ratio:.1%}). Ensure data is current.")
            else:
                logger.info(f"Predictive targets validated. Ready for modeling.")

        else:
            logger.error("Task 07 Checkpoint: FAILED. Insufficient row/ticker count.")

    except Exception as e:
        logger.error(f"Task 07 Checkpoint: FAILED. Database error: {e}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()