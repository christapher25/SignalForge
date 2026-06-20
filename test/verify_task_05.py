import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
import config


def verify():
    logger.debug("Executing Task 05 Verification")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    try:
        query = """
        SELECT 
            COUNT(*) as total_rows,
            SUM(CASE WHEN vader_sentiment IS NOT NULL THEN 1 ELSE 0 END) as vader_count,
            SUM(CASE WHEN finbert_sentiment IS NOT NULL THEN 1 ELSE 0 END) as finbert_count
        FROM news
        """
        stats = pd.read_sql(query, engine).iloc[0]

        logger.info("Task 05 Verification SQL executed.")
        logger.info(f"Total rows in news table: {stats['total_rows']}")
        logger.info(f"Rows with VADER sentiment: {stats['vader_count']}")
        logger.info(f"Rows with FinBERT sentiment: {stats['finbert_count']}")

        if stats['total_rows'] > 0 and stats['total_rows'] == stats['finbert_count']:
            logger.info("Task 05 Checkpoint: SUCCESS. All news rows processed with sentiment.")
        elif stats['finbert_count'] > 0:
            logger.warning(
                f"Task 05 Checkpoint: PARTIAL. {stats['finbert_count']}/{stats['total_rows']} rows processed.")
        else:
            logger.error("Task 05 Checkpoint: FAILED. No sentiment data found.")

    except Exception as e:
        logger.error(f"Task 05 Checkpoint: FAILED. Database error: {e}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()