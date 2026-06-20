import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
import config


def verify():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    try:
        inspector = inspect(engine)
        if 'signals' not in inspector.get_table_names():
            logger.error(
                "Task 08 Checkpoint: FAILED. Table 'signals' does not exist yet. Run signal_generator.py first.")
            return

        total_rows = pd.read_sql("SELECT COUNT(*) FROM signals", engine).iloc[0, 0]

        logger.info("Task 08 Verification executed.")

        if total_rows == 0:
            logger.info(
                "Task 08 Checkpoint: SUCCESS. Table exists but is perfectly empty. (The model determined no stocks met the elite threshold today. This is a valid system state).")
        else:
            query = text("""
            SELECT signal, COUNT(*) as count 
            FROM signals 
            WHERE date = (SELECT MAX(date) FROM signals)
            GROUP BY signal
            """)

            with engine.connect() as conn:
                df = pd.read_sql(query, conn)

            logger.info("Task 08 Checkpoint: SUCCESS. Signals successfully generated in DB.")
            for _, row in df.iterrows():
                logger.info(f"Signal: {row['signal']} | Count: {row['count']}")

    except Exception as e:
        logger.error(f"Task 08 Checkpoint: FAILED. Database error: {e}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()