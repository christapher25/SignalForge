# ml/prepare_labels.py
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def build_triple_barrier_targets(pt_sl_mult=[1.0, 2.0], holding_period=4):
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    logger.info("Loading dataset into RAM to bypass SQLite I/O locks...")
    features_df = pd.read_sql("SELECT * FROM features ORDER BY ticker, date ASC", engine)
    ohlcv_df = pd.read_sql("SELECT ticker, date, close FROM ohlcv ORDER BY ticker, date ASC", engine)

    logger.info("Merging price data in memory...")
    df = pd.merge(features_df, ohlcv_df[['ticker', 'date', 'close']], on=['ticker', 'date'], how='left')

    if df.empty:
        raise ValueError("No feature rows available.")

    logger.info(
        f"Calculating Triple-Barrier paths (TP: {pt_sl_mult[0]}x, SL: {pt_sl_mult[1]}x, Period: {holding_period})...")
    df['atr_usd'] = df['close'] * df['atr_norm']

    all_labels = np.zeros(len(df), dtype=int)

    grouped = df.groupby('ticker')
    for ticker, indices in grouped.groups.items():
        group_indices = indices.to_numpy()
        closes = df.loc[group_indices, 'close'].to_numpy()
        atrs = df.loc[group_indices, 'atr_usd'].to_numpy()

        for i in range(len(group_indices) - holding_period):
            entry_p = closes[i]
            atr_window = atrs[i]

            if pd.isna(entry_p) or pd.isna(atr_window) or atr_window <= 0:
                continue

            tp_barrier = entry_p + (pt_sl_mult[0] * atr_window)
            sl_barrier = entry_p - (pt_sl_mult[1] * atr_window)

            forward_closes = closes[i + 1: i + 1 + holding_period]

            triggered = False
            for price in forward_closes:
                if price >= tp_barrier:
                    all_labels[group_indices[i]] = 1
                    triggered = True
                    break
                elif price <= sl_barrier:
                    all_labels[group_indices[i]] = 0
                    triggered = True
                    break

            if not triggered:
                all_labels[group_indices[i]] = 1 if forward_closes[-1] > entry_p else 0

    logger.info("Assigning computed targets...")
    df['structural_target'] = all_labels
    df = df.drop(columns=['close', 'atr_usd'])

    logger.info("Performing high-speed bulk replacement of the features table...")
    df.to_sql("features", engine, if_exists="replace", index=False, chunksize=100000)

    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_feat_ticker_date ON features(ticker, date);"))

    logger.success("Structural Triple-Barrier targets successfully generated and bulk-saved.")


if __name__ == "__main__":
    build_triple_barrier_targets(pt_sl_mult=[1.0, 2.0], holding_period=4)