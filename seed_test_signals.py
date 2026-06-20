import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def seed_fake_signals():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # Set date to 4 days ago so outcome_recorder can look at the "future" 3 days
    past_date = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S')

    # Create a dummy 20-feature snapshot that XGBoost expects
    dummy_features = json.dumps({
        "rsi_14": 45.0, "macd_delta": 0.1, "bb_position": 0.5, "atr_norm": 0.02,
        "adx_14": 25.0, "obv_trend": 1.0, "volume_ratio": 1.2, "dist_52w_high": 0.1,
        "dist_52w_low": 0.5, "fed_rate": 5.25, "cpi": 3.1, "vix": 15.0,
        "spy_above_200ema": 1, "vader_sentiment": 0.2, "finbert_sentiment": 0.8,
        "sector_etf_momentum": 0.05, "earnings_days_away": 15, "pe_ratio_vs_sector": -2.0,
        "fundamental_score": 50.0, "market_context_score": 60.0
    })

    # Pick AAPL because we know it has OHLCV data to grade against
    fake_signals = []
    for i in range(25):
        fake_signals.append({
            "ticker": "AAPL",
            "timestamp": past_date,
            "mode": "INTRADAY",
            "action": "BUY",
            "entry": 180.00 + (i * 0.1),  # Slight variation
            "target": 185.00,
            "stop_loss": 178.00,
            "confidence": 85.0,
            "feature_snapshot": dummy_features
        })

    with engine.begin() as conn:
        stmt = text("""
            INSERT INTO signals (ticker, timestamp, mode, action, entry, target, stop_loss, confidence, feature_snapshot)
            VALUES (:ticker, :timestamp, :mode, :action, :entry, :target, :stop_loss, :confidence, :feature_snapshot)
        """)
        conn.execute(stmt, fake_signals)

    logger.success(f"Injected 25 time-traveled signals into the database for {past_date}.")


if __name__ == "__main__":
    seed_fake_signals()