import sys
import json
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
import ta
from loguru import logger
from sqlalchemy import create_engine, text, inspect
from tqdm import tqdm
from tenacity import retry, wait_exponential, stop_after_attempt

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def fetch_ohlcv(engine, ticker):
    query = text("SELECT date, open, high, low, close, volume FROM ohlcv WHERE ticker = :ticker ORDER BY date ASC")
    return pd.read_sql(query, engine, params={"ticker": ticker})


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure datatypes for ta
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close', 'high', 'low', 'volume']).copy()

    if len(df) < 200:
        return pd.DataFrame()

    try:
        # RSI
        df['rsi_14'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

        # MACD
        macd_inst = ta.trend.MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
        df['macd'] = macd_inst.macd()
        df['macd_signal'] = macd_inst.macd_signal()
        df['macd_delta'] = macd_inst.macd_diff()

        # Bollinger Bands
        bb_inst = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb_inst.bollinger_hband()
        df['bb_lower'] = bb_inst.bollinger_lband()
        df['bb_position'] = bb_inst.bollinger_pband()

        # ATR
        atr_inst = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        df['atr_14'] = atr_inst.average_true_range()
        df['atr_normalized'] = df['atr_14'] / df['close']

        # ADX
        adx_inst = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
        df['adx_14'] = adx_inst.adx()

        # OBV & Trend
        obv_inst = ta.volume.OnBalanceVolumeIndicator(close=df['close'], volume=df['volume'])
        df['obv'] = obv_inst.on_balance_volume()
        df['obv_trend_5d'] = (df['obv'] - df['obv'].shift(5)) / 5

        # EMA 200
        ema_inst = ta.trend.EMAIndicator(close=df['close'], window=200)
        df['ema_200'] = ema_inst.ema_indicator()

        # Volume Ratio
        sma_vol = df['volume'].rolling(window=20, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / sma_vol

        # 52-Week High/Low (Assuming ~252 trading days)
        df['high_52w'] = df['high'].rolling(window=252, min_periods=1).max()
        df['low_52w'] = df['low'].rolling(window=252, min_periods=1).min()

        df['dist_from_52w_high'] = (df['close'] - df['high_52w']) / df['high_52w']
        df['dist_from_52w_low'] = (df['close'] - df['low_52w']) / df['low_52w']

        df = df.dropna()
        return df

    except Exception as e:
        logger.error(f"Indicator calculation failed: {e}")
        return pd.DataFrame()


def ensure_table_schema(engine):
    inspector = inspect(engine)
    if 'indicators' in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE indicators"))

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE indicators (
                ticker TEXT, date DATE, rsi_14 REAL, macd REAL, macd_signal REAL, macd_delta REAL,
                bb_upper REAL, bb_lower REAL, bb_position REAL, atr_14 REAL, atr_normalized REAL,
                adx_14 REAL, obv REAL, obv_trend_5d REAL, ema_200 REAL, volume_ratio REAL,
                dist_from_52w_high REAL, dist_from_52w_low REAL,
                PRIMARY KEY (ticker, date)
            )
        """))
    logger.info("Indicators table schema verified and created.")


def run_indicators_pipeline():
    logger.debug("Starting indicators pipeline")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = config.PROCESSED_DIR / 'indicators_checkpoint.json'

    try:
        ensure_table_schema(engine)
    except Exception as e:
        logger.error(f"Failed to setup database: {e}")
        sys.exit(1)

    universe_files = sorted(list(config.CONSTITUENTS_DIR.glob("sp500_*.json")), reverse=True)
    with open(universe_files[0], 'r') as f:
        all_tickers = json.load(f)

    # Force a fresh run by ignoring any old checkpoints
    processed_tickers = set()

    pending_tickers = [t for t in all_tickers if t not in processed_tickers]
    logger.info(f"Processing indicators for {len(pending_tickers)} pending tickers.")

    for i in tqdm(range(0, len(pending_tickers), 50), desc="Indicator Batches"):
        batch = pending_tickers[i:i + 50]
        batch_dfs = []
        successful_tickers = []

        for ticker in batch:
            df_ohlcv = fetch_ohlcv(engine, ticker)
            df_ind = compute_indicators(df_ohlcv)

            if not df_ind.empty:
                df_ind['ticker'] = ticker
                # Select only the required columns for DB insertion
                cols = ['ticker', 'date', 'rsi_14', 'macd', 'macd_signal', 'macd_delta',
                        'bb_upper', 'bb_lower', 'bb_position', 'atr_14', 'atr_normalized',
                        'adx_14', 'obv', 'obv_trend_5d', 'ema_200', 'volume_ratio',
                        'dist_from_52w_high', 'dist_from_52w_low']
                batch_dfs.append(df_ind[cols])
            else:
                logger.debug(f"{ticker}: Skipped (insufficient data or calc failure)")

            successful_tickers.append(ticker)

        if batch_dfs:
            final_df = pd.concat(batch_dfs, ignore_index=True)
            try:
                with engine.begin() as conn:
                    # Idempotent write
                    tickers_in_df = tuple(final_df['ticker'].unique())
                    if len(tickers_in_df) == 1:
                        conn.execute(text(f"DELETE FROM indicators WHERE ticker = '{tickers_in_df[0]}'"))
                    else:
                        conn.execute(text(f"DELETE FROM indicators WHERE ticker IN {tickers_in_df}"))

                    b_count = conn.execute(text("SELECT COUNT(*) FROM indicators")).scalar()
                    final_df.to_sql('indicators', con=conn, if_exists='append', index=False)
                    a_count = conn.execute(text("SELECT COUNT(*) FROM indicators")).scalar()

                    if a_count <= b_count and len(final_df) > 0:
                        logger.error(f"Silent DB failure for indicator batch {i}")
                    else:
                        logger.info(f"Wrote {a_count - b_count} indicator rows to DB")
            except Exception as e:
                logger.error(f"Database transaction failed for indicator batch {i}: {e}")
                continue

        processed_tickers.update(successful_tickers)
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(list(processed_tickers), f)
        except Exception:
            pass

    logger.info("Indicators pipeline completed successfully.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    run_indicators_pipeline()