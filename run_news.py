# run_news.py
import sys
import time
from pathlib import Path
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from delivery.scheduler import run_live_news_refresh

if __name__ == "__main__":
    # Calculate exactly 8 hours in seconds
    EIGHT_HOURS = 8 * 60 * 60

    logger.info("Starting background news ingestion scheduler (8-hour intervals)...")
    logger.info("This system runs 24/7, including weekends, to maintain macro awareness.")

    while True:
        try:
            logger.info("Initiating scheduled news refresh...")
            run_live_news_refresh()

            logger.success("News refresh cycle complete. System sleeping for 8 hours...")
            time.sleep(EIGHT_HOURS)

        except Exception as e:
            logger.error(f"News background loop encountered an execution error: {e}")
            logger.info("Retrying in 5 minutes...")
            time.sleep(300)  # Wait 5 minutes before retrying on failure