import sys
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
from loguru import logger
from sqlalchemy import create_engine, text
from tqdm import tqdm
import ta

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config


def build_indicators():
    logger.info("Building Normalized Technical Indicators...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    df = pd.read_sql("SELECT * FROM ohlcv ORDER BY date ASC", engine)
    if df.empty:
        logger.error("OHLCV table is empty.")
        return

    df['date'] = pd.to_datetime(df['date'])
    tickers = df['ticker'].unique()
    results = []

    for ticker in tqdm(tickers, desc="Calculating Normalized Indicators"):
        ticker_df = df[df['ticker'] == ticker].copy()
        ticker_df.set_index('date', inplace=True)
        ticker_df.sort_index(inplace=True)

        if len(ticker_df) < 200:
            continue

        try:
            # 1. RSI (Already Normalized 0-100)
            ticker_df['rsi_14'] = ta.momentum.RSIIndicator(close=ticker_df['close'], window=14).rsi()


            # 2. PPO (Percentage Price Oscillator - Replaces Raw MACD Dollars)
            ema_12 = ta.trend.EMAIndicator(close=ticker_df['close'], window=12).ema_indicator()
            ema_26 = ta.trend.EMAIndicator(close=ticker_df['close'], window=26).ema_indicator()

            # PPO = (EMA(12) - EMA(26)) / EMA(26) * 100
            ticker_df['ppo'] = ((ema_12 - ema_26) / ema_26) * 100
            ticker_df['ppo_signal'] = ticker_df['ppo'].ewm(span=9, adjust=False).mean()
            ticker_df['ppo_hist'] = ticker_df['ppo'] - ticker_df['ppo_signal']

            # 3. Normalized Moving Average Distances
            ticker_df['dist_sma_20'] = (ticker_df['close'] / ta.trend.SMAIndicator(close=ticker_df['close'],
                                                                                   window=20).sma_indicator()) - 1
            ticker_df['dist_sma_50'] = (ticker_df['close'] / ta.trend.SMAIndicator(close=ticker_df['close'],
                                                                                   window=50).sma_indicator()) - 1
            ticker_df['dist_sma_200'] = (ticker_df['close'] / ta.trend.SMAIndicator(close=ticker_df['close'],
                                                                                    window=200).sma_indicator()) - 1

            # 4. Bollinger Bands (Position and Width are scale-invariant)
            bb = ta.volatility.BollingerBands(close=ticker_df['close'], window=20, window_dev=2)
            ticker_df['bb_position'] = bb.bollinger_pband()
            ticker_df['bb_width_norm'] = bb.bollinger_wband()

            # 5. Normalized Volatility (ATR as a percentage of price)
            atr = ta.volatility.AverageTrueRange(high=ticker_df['high'], low=ticker_df['low'], close=ticker_df['close'],
                                                 window=14)
            ticker_df['atr_norm'] = atr.average_true_range() / ticker_df['close']

            # 6. OBV Z-Score (Replaces raw cumulative OBV volume)
            obv = ta.volume.OnBalanceVolumeIndicator(close=ticker_df['close'],
                                                     volume=ticker_df['volume']).on_balance_volume()
            obv_sma = obv.rolling(20).mean()
            obv_std = obv.rolling(20).std()
            ticker_df['obv_zscore'] = np.where(obv_std == 0, 0, (obv - obv_sma) / obv_std)

            # 7. Volume Ratio & Momentum
            ticker_df['volume_ratio'] = ticker_df['volume'] / ticker_df['volume'].rolling(20).mean()
            ticker_df['return_1d'] = ticker_df['close'].pct_change(1)
            ticker_df['return_5d'] = ticker_df['close'].pct_change(5)

            ticker_df.reset_index(inplace=True)
            results.append(ticker_df)

        except Exception as e:
            logger.warning(f"Failed indicator math for {ticker}: {e}")

    final_df = pd.concat(results, ignore_index=True)

    # Keep only the date, ticker, and the pure normalized features
    cols_to_keep = [
        'date', 'ticker', 'rsi_14', 'ppo', 'ppo_signal', 'ppo_hist',
        'dist_sma_20', 'dist_sma_50', 'dist_sma_200', 'bb_position',
        'bb_width_norm', 'atr_norm', 'obv_zscore', 'volume_ratio',
        'return_1d', 'return_5d'
    ]

    final_df = final_df[cols_to_keep].dropna()
    final_df['date'] = final_df['date'].dt.date

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS indicators"))
        final_df.to_sql('indicators', con=conn, index=False)

    logger.success("Normalized Indicators securely written to database.")


if __name__ == "__main__":
    build_indicators()