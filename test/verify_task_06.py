import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
import config


def verify():
    logger.debug("Executing Task 06 Verification")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    try:
        query = text("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(finbert_sentiment) as finbert_count
        FROM news
        """)

        with engine.connect() as conn:
            stats = pd.read_sql(query, conn).iloc[0]

        total_rows = int(stats['total_rows'])
        finbert_count = int(stats['finbert_count'])

        logger.info("Task 06 Verification SQL executed.")
        logger.info(f"Total rows in news table: {total_rows}")
        logger.info(f"Rows with FinBERT sentiment: {finbert_count}")

        if total_rows > 50000 and total_rows == finbert_count:
            logger.info("Task 06 Checkpoint: SUCCESS. All news rows processed with FinBERT sentiment (>50,000).")
        elif finbert_count > 0:
            logger.warning(
                f"Task 06 Checkpoint: PARTIAL. {finbert_count}/{total_rows} rows processed, or total < 50000.")
        else:
            logger.error("Task 06 Checkpoint: FAILED. No sentiment data found or table is empty.")

    except Exception as e:
        logger.error(f"Task 06 Checkpoint: FAILED. Database error: {e}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()