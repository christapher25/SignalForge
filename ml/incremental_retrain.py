import sys
import json
import joblib
import pandas as pd
import xgboost as xgb
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def incremental_retrain():
    logger.info("Initializing Daily Incremental Retrain Sequence...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    state_file = config.PROCESSED_DIR / "last_retrain.json"
    last_retrain = "2000-01-01 00:00:00"
    if state_file.exists():
        with open(state_file, "r") as f:
            last_retrain = json.load(f).get("timestamp", last_retrain)

    try:
        with engine.connect() as conn:
            query = text("""
                SELECT feature_snapshot, actual_outcome
                FROM signals
                WHERE actual_outcome IS NOT NULL
                AND timestamp > :last_time
                AND feature_snapshot IS NOT NULL
            """)
            new_data = pd.read_sql(query, conn, params={"last_time": last_retrain})

        if len(new_data) < getattr(config, "MIN_OUTCOMES_FOR_RETRAIN", 20):
            logger.info(f"Only {len(new_data)} new verified outcomes found. Minimum is 20. Retrain skipped.")
            return

        logger.info(f"Found {len(new_data)} new outcomes. Preparing to update XGBoost model...")

        features_list = []
        labels = []

        for _, row in new_data.iterrows():
            try:
                feats = json.loads(row['feature_snapshot'])
                features_list.append(feats)
                labels.append(row['actual_outcome'])
            except Exception:
                continue

        if not features_list:
            return

        df_features = pd.DataFrame(features_list)
        y = pd.Series(labels)

        model_path = config.MODELS_DIR / "signal_model.pkl"
        if not model_path.exists():
            logger.warning(
                f"Base model not found at {model_path}. Cannot incrementally retrain until base model is built.")
            return

        model_data = joblib.load(model_path)
        xgb_model = model_data['model'] if isinstance(model_data, dict) and 'model' in model_data else model_data

        dtrain = xgb.DMatrix(df_features, label=y)
        logger.info("Updating XGBoost trees with new live market patterns...")

        if hasattr(xgb_model, 'get_booster'):
            booster = xgb_model.get_booster()
        else:
            booster = xgb_model

        booster.update(dtrain, getattr(booster, 'best_iteration', 0))

        joblib.dump(model_data, model_path)

        with open(state_file, "w") as f:
            json.dump({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f)

        logger.success(f"Retrain complete. Injected {len(new_data)} new market samples into the AI's memory.")

    except Exception as e:
        logger.error(f"Incremental retrain failed: {e}")


if __name__ == "__main__":
    incremental_retrain()