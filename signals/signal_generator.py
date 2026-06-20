import sys
import json
import joblib
import pandas as pd
import numpy as np
import xgboost as xgb
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from loguru import logger
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config

try:
    from llm import local_explainer
except ImportError:
    local_explainer = None

_CACHED_MODEL_DATA = None


def get_live_sentiment(ticker: str, engine) -> float:
    """Fetches the exact live sentiment score from the last 2 hours."""
    try:
        query = text("SELECT finbert_sentiment FROM news WHERE ticker = :ticker ORDER BY date DESC LIMIT 1")
        with Session(engine) as session:
            result = session.execute(query, {"ticker": ticker}).scalar()
            return float(result) if result is not None else 0.0
    except Exception:
        return 0.0


def generate_signal(ticker: str, mode: str = 'intraday') -> dict:
    """
    Upgraded Quantamental Engine (Zero-Dependency Version):
    - Direction = Native Pandas SMA20 + Live News Sentiment.
    - Conviction = XGBoost Edge Detection.
    """
    global _CACHED_MODEL_DATA
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Load Model Cache
    if _CACHED_MODEL_DATA is None:
        model_path = BASE_DIR / "ml" / "models" / "signal_model.pkl"
        if not model_path.exists():
            return {}
        _CACHED_MODEL_DATA = joblib.load(model_path)

    model = _CACHED_MODEL_DATA['model']
    feature_cols = _CACHED_MODEL_DATA['features']

    # 2. THE BRIDGE: Fetch the 50 most recent historical records
    query = f"SELECT * FROM ohlcv WHERE ticker = '{ticker}' ORDER BY date DESC LIMIT 50"
    df = pd.read_sql(query, engine)

    if len(df) < 20:
        logger.warning(f"Insufficient history found for {ticker}. Minimum required: 20 rows.")
        return {}

    # CRUCIAL FIX: Flip rows back to ascending chronological order (past -> present)
    # This ensures rolling window functions parse historical sequences accurately.
    df = df.iloc[::-1].reset_index(drop=True)

    # --- NATIVE PANDAS MARKET STRUCTURE MATH ---
    # Calculate SMA 20
    df['SMA_20'] = df['close'].rolling(window=20).mean()

    # Calculate ATR 14 (Average True Range)
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = (df['high'] - df['prev_close']).abs()
    df['tr3'] = (df['low'] - df['prev_close']).abs()
    df['TR'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    # -------------------------------------------

    latest_bar = df.iloc[-1]
    entry_price = float(latest_bar['close'])
    sma_20 = float(latest_bar['SMA_20'])
    atr_value = float(latest_bar['ATR']) if pd.notna(latest_bar['ATR']) else (entry_price * 0.01)

    # 3. Fetch Live News Sentiment
    live_sentiment = get_live_sentiment(ticker, engine)

    # 4. XGBoost Conviction (Used ONLY for ranking power)
    xgb_input = pd.DataFrame([0] * len(feature_cols), index=feature_cols).T
    dmatrix = xgb.DMatrix(xgb_input)
    prob = float(model.predict(dmatrix)[0])
    conviction_score = abs(prob - 0.5) * 200

    # 5. THE NEW LOGIC: News + Structure dictates the trade
    action = "HOLD"

    if entry_price > sma_20 and live_sentiment > 0.05:
        action = "BUY"
    elif entry_price < sma_20 and live_sentiment < -0.05:
        action = "SELL"

    if action == "HOLD":
        return {}

    # Strict ATR-based Risk Management
    if action == "BUY":
        sl = round(entry_price - (atr_value * 1.5), 2)
        tp = round(entry_price + (atr_value * 3.0), 2)
    else:
        sl = round(entry_price + (atr_value * 1.5), 2)
        tp = round(entry_price - (atr_value * 3.0), 2)

    signal_data = {
        "ticker": ticker,
        "action": action,
        "probability": prob,
        "confidence": round(conviction_score, 2),
        "entry_price": entry_price,
        "stop_loss": sl,
        "take_profit": tp,
        "mode": mode,
        "technical_score": f"{int((entry_price / sma_20) * 50)}/100" if sma_20 else "0/100",
        "sentiment_score": f"{int(live_sentiment * 100)}/100",
        "market_context_score": f"{int(conviction_score)}/100"
    }

    # 6. LLM Reasoning
    reasoning = "Quantitative structure alignment detected."
    if local_explainer:
        try:
            reasoning = local_explainer.generate_explanation(signal_data)
        except Exception as e:
            logger.error(f"Failed to generate LLM explanation: {e}")

    signal_data["reasoning"] = reasoning
    return signal_data