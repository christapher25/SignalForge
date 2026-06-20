# verify_status.py
import sys
from unittest.mock import MagicMock

# =====================================================================
# THE ULTRA WORKAROUND: Mock chromadb instantly before any other import
# occurs. This stops onnxruntime from initializing and crashing.
# =====================================================================
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()

import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from signals.signal_generator import generate_signal


def get_isolated_universe(engine) -> list:
    """Queries tickers directly from SQLite to avoid scheduler imports."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT DISTINCT ticker FROM features"))
            tickers = [row[0] for row in result.fetchall()]
        return tickers if tickers else ['AAPL', 'MSFT', 'NVDA']
    except Exception as e:
        logger.error(f"Failed to fetch universe: {e}")
        return ['AAPL', 'MSFT', 'NVDA']


def verify_walk_forward(engine):
    """Prints the 15 walk-forward validation records."""
    logger.info("--- VERIFYING WALK-FORWARD RESULTS ---")
    try:
        query = "SELECT window_id, test_year, accuracy, auc FROM walk_forward_results ORDER BY window_id;"
        df = pd.read_sql(query, engine)
        if df.empty:
            logger.warning("Table exists but contains 0 rows.")
        else:
            print("\n" + df.to_string(index=False) + "\n")
            logger.info(f"Total Rows Verified: {len(df)}")
    except Exception as e:
        logger.error(f"Failed to query walk_forward_results: {e}")


def run_test_scan(engine):
    """Runs a localized scan to count daily output volume across the universe."""
    logger.info("--- EXECUTING LIVE SIGNAL VOLUME TEST ---")
    tickers = get_isolated_universe(engine)
    signals_generated = []

    logger.info(f"Scanning {len(tickers)} assets through local CPU-bound XGBoost...")
    for ticker in tickers:
        try:
            sig = generate_signal(ticker, mode="INTRADAY")
            if sig and sig.get('action') in ["BUY", "SELL"]:
                signals_generated.append(sig)
        except Exception:
            pass

    if not signals_generated:
        logger.warning("Zero signals generated during this scan.")
        return

    df = pd.DataFrame(signals_generated)
    cols = [c for c in ['ticker', 'action', 'confidence', 'entry_price'] if c in df.columns]
    df = df[cols].sort_values(by='confidence', ascending=False)

    print("\n" + df.to_string(index=False) + "\n")
    logger.info(f"Total Signals Generated Today: {len(df)}")


if __name__ == "__main__":
    db_engine = create_engine(f"sqlite:///{config.DB_PATH}")
    verify_walk_forward(db_engine)
    run_test_scan(db_engine)