import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def ensure_schema(engine):
    with engine.begin() as conn:
        try:
            conn.execute(text("SELECT actual_outcome FROM signals LIMIT 1"))
        except Exception:
            conn.execute(text("ALTER TABLE signals ADD COLUMN actual_outcome INTEGER"))
        try:
            conn.execute(text("SELECT pct_change_actual FROM signals LIMIT 1"))
        except Exception:
            conn.execute(text("ALTER TABLE signals ADD COLUMN pct_change_actual REAL"))


def record_outcomes():
    logger.info("Initializing Daily Outcome Recorder...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    ensure_schema(engine)

    target_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
    target_end = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d 23:59:59')

    try:
        with engine.connect() as conn:
            query = text("""
                SELECT rowid AS id, ticker, timestamp, action, entry
                FROM signals
                WHERE actual_outcome IS NULL
                AND action IN ('BUY', 'SELL')
                AND timestamp BETWEEN :start AND :end
            """)
            pending_signals = pd.read_sql(query, conn, params={"start": target_start, "end": target_end})

        if pending_signals.empty:
            logger.info("No pending signals require grading today.")
            return

        logger.info(f"Found {len(pending_signals)} pending signals to grade.")
        updates = []

        for _, sig in pending_signals.iterrows():
            sig_id = sig['id']
            ticker = sig['ticker']
            action = sig['action']
            entry = sig['entry']

            sig_date = str(sig['timestamp'])[:10]

            if not entry or entry <= 0:
                continue

            with engine.connect() as conn:
                price_query = text("""
                    SELECT high, low, close
                    FROM ohlcv
                    WHERE ticker = :ticker AND date > :sig_date
                    ORDER BY date ASC LIMIT 3
                """)
                prices = pd.read_sql(price_query, conn, params={"ticker": ticker, "sig_date": sig_date})

            if prices.empty:
                continue

            max_high = prices['high'].max()
            min_low = prices['low'].min()
            final_close = prices['close'].iloc[-1]

            outcome = 0
            pct_change = (final_close - entry) / entry

            if action == 'BUY' and max_high >= (entry * 1.02):
                outcome = 1
            elif action == 'SELL' and min_low <= (entry * 0.98):
                outcome = 1

            updates.append({
                "id": int(sig_id),
                "outcome": outcome,
                "pct_change": float(pct_change)
            })

        if updates:
            with engine.begin() as conn:
                stmt = text("""
                    UPDATE signals
                    SET actual_outcome = :outcome, pct_change_actual = :pct_change
                    WHERE rowid = :id
                """)
                conn.execute(stmt, updates)
            logger.success(f"Graded and recorded {len(updates)} signal outcomes.")

    except Exception as e:
        logger.error(f"Outcome recording failed: {e}")


if __name__ == "__main__":
    record_outcomes()