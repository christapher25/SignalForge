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

    try:
        count_query = "SELECT COUNT(*) as c FROM news"
        dates_query = "SELECT MIN(date) as min_date, MAX(date) as max_date FROM news"

        total_rows = pd.read_sql(count_query, engine).iloc[0]['c']
        dates = pd.read_sql(dates_query, engine).iloc[0]

        logger.info("Task 04 Verification SQL executed.")
        logger.info(f"Total rows in news table: {total_rows}")
        logger.info(f"Date range: {dates['min_date']} to {dates['max_date']}")

        if total_rows >= 50000:
            logger.info("Task 04 Checkpoint: SUCCESS. News database densely populated (> 50,000 rows).")
        elif total_rows > 0:
            logger.warning(f"Task 04 Checkpoint: PARTIAL. Found {total_rows} rows, goal is >= 50,000.")
        else:
            logger.error("Task 04 Checkpoint: FAILED. News table is entirely empty.")

    except Exception as e:
        logger.error(f"Task 04 Checkpoint: FAILED. Database error: {e}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()