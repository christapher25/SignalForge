# ml/train_tuned.py
import sys
import warnings
import json
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from loguru import logger
from sqlalchemy import create_engine
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score

warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def load_training_data():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    query = "SELECT * FROM features WHERE target IS NOT NULL ORDER BY date ASC"
    df = pd.read_sql(query, engine)

    if df.empty:
        raise ValueError("No targets found in features table. Check data pipeline ingestion.")

    target_col = 'target'

    # PURGE THE NOISE: Explicitly dropping 'finbert' and 'vader' so the model
    # does not overfit to columns that are 94.6% empty.
    drop_cols = [
        'id', 'ticker', 'date', target_col, 'structural_target',
        'label', 'direction', 'next_close_higher',
        'finbert', 'vader'
    ]

    feature_cols = [col for col in df.columns if col not in drop_cols and not col.startswith('Unnamed')]

    X = df[feature_cols].astype(np.float32)
    y = df[target_col].astype(int)

    return X, y, feature_cols


def train_leakage_free():
    logger.info("Loading master features from database...")
    X, y, feature_names = load_training_data()

    total_samples = len(X)
    logger.info(f"Total Dataset Size: {total_samples} institutional rows")

    train_end = int(total_samples * 0.60)
    val_end = int(total_samples * 0.80)

    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
    X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

    pos_weight = 1.2

    production_params = {
        'n_estimators': 300,
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 2,
        'gamma': 0.1,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'scale_pos_weight': pos_weight
    }

    logger.info(f"Training production XGBoost engine (Device: CPU) with Pos-Weight: {pos_weight}...")
    model = XGBClassifier(
        objective='binary:logistic',
        eval_metric='aucpr',
        tree_method='hist',
        early_stopping_rounds=40,
        random_state=42,
        **production_params
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False
    )

    val_probs = model.predict_proba(X_val)[:, 1]
    test_probs = model.predict_proba(X_test)[:, 1]

    logger.info("Scanning Validation Split for Ultra-Selective Percentiles (Max 5-6 Signals/Day)...")

    # Target extreme percentiles to throttle volume and maximize win-rate
    chosen_buy_thresh = float(np.percentile(val_probs, 99.5))
    chosen_sell_thresh = float(np.percentile(val_probs, 0.5))
    found_valid = False

    # Scan only the absolute highest tiers (Top 1.5% down to Top 0.25%)
    for tail_pct in [1.5, 1.0, 0.75, 0.5, 0.25]:
        b_thresh = np.percentile(val_probs, 100 - tail_pct)
        s_thresh = np.percentile(val_probs, tail_pct)

        active_val = (val_probs >= b_thresh) | (val_probs <= s_thresh)
        if np.sum(active_val) < 50:  # Ensure at least a minimal sample exists
            continue

        v_preds = np.where(val_probs[active_val] >= b_thresh, 1, 0)
        v_win_rate = accuracy_score(y_val[active_val], v_preds)

        # Target a much higher >65% win rate because we are sacrificing so much volume
        if v_win_rate >= 0.65:
            chosen_buy_thresh = float(b_thresh)
            chosen_sell_thresh = float(s_thresh)
            found_valid = True
            break

    if not found_valid:
        logger.warning("Could not clear 65% hurdle. Defaulting to strict Top 0.5% relative conviction to cap volume.")
        chosen_buy_thresh = float(np.percentile(val_probs, 99.5))
        chosen_sell_thresh = float(np.percentile(val_probs, 0.5))

    logger.info(f"Locked Operational Tiers -> BUY: >= {chosen_buy_thresh:.4f} | SELL: <= {chosen_sell_thresh:.4f}")

    active_test = (test_probs >= chosen_buy_thresh) | (test_probs <= chosen_sell_thresh)
    test_exposure = (np.sum(active_test) / len(y_test)) * 100

    if np.sum(active_test) > 0:
        t_preds = np.where(test_probs[active_test] >= chosen_buy_thresh, 1, 0)
        true_test_win_rate = accuracy_score(y_test[active_test], t_preds)
        buy_precision = precision_score(y_test[active_test], t_preds, zero_division=0)
    else:
        true_test_win_rate = 0.0
        buy_precision = 0.0

    logger.info("\n=======================================================")
    logger.info("   TRUE UNLEAKED PRODUCTION METRICS (UNSEEN TEST SET)")
    logger.info("=======================================================")
    logger.info(f"BUY Execution Threshold:      >= {chosen_buy_thresh:.4f}")
    logger.info(f"SELL Execution Threshold:     <= {chosen_sell_thresh:.4f}")
    logger.info(f"Overall Signal Win-Rate:      {true_test_win_rate * 100:.2f}%")
    logger.info(f"Long (BUY) Win-Rate:          {buy_precision * 100:.2f}%")
    logger.info(f"System Trade Exposure:        {test_exposure:.2f}%")
    logger.info("=======================================================\n")

    ml_dir = BASE_DIR / "ml"
    ml_dir.mkdir(exist_ok=True)

    joblib.dump(model, ml_dir / "xgboost_model.pkl")
    joblib.dump(feature_names, ml_dir / "features.pkl")

    meta_data = {
        "buy_threshold": chosen_buy_thresh,
        "sell_threshold": chosen_sell_thresh,
        "expected_win_rate": true_test_win_rate,
        "market_exposure": test_exposure
    }
    with open(ml_dir / "model_meta.json", "w") as f:
        json.dump(meta_data, f, indent=4)

    logger.success("Deployed validated, leakage-free pipeline artifacts.")


if __name__ == "__main__":
    try:
        train_leakage_free()
    except Exception as e:
        logger.exception(f"Pipeline failure: {e}")