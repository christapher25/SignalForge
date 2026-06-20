# fix_db.py
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def add_uuid_column():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Check if the column already exists
    try:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(news)"))
            columns = [row[1] for row in result.fetchall()]

        if 'uuid' in columns:
            logger.info("'uuid' column already exists in 'news' table. No action needed.")
            return

    except Exception as e:
        logger.error(f"Failed to read table schema: {e}")
        return

    # 2. Alter the table to add the column
    try:
        logger.info("Adding 'uuid' column to the 'news' table...")
        with engine.connect() as conn:
            # We add it as TEXT. We don't set UNIQUE or NOT NULL here because existing rows
            # won't have a UUID, and SQLite gets angry if we force constraints on old data.
            conn.execute(text("ALTER TABLE news ADD COLUMN uuid TEXT;"))
            conn.commit()
        logger.success("Schema updated successfully! You can now run your ChromaDB sync.")

    except Exception as e:
        logger.error(f"Failed to alter table: {e}")


if __name__ == "__main__":
    add_uuid_column()