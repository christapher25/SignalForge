import sys
import json
import joblib
from pathlib import Path
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sqlalchemy import create_engine
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
import config


def train_model():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    windows_path = BASE_DIR / "ml" / "windows.json"

    with open(windows_path, "r") as f:
        windows = json.load(f)

    logger.info("Loading full feature matrix into memory...")
    df = pd.read_sql("SELECT * FROM feature_matrix", engine)

    df['date'] = df['date'].astype(str).str[:10]
    features = [c for c in df.columns if c not in ['ticker', 'date', 'target', 'next_close']]

    # ---------------------------------------------------------
    # FIXED-ROUND QUANT PARAMETERS
    # ---------------------------------------------------------
    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'tree_method': 'hist',
        'learning_rate': 0.02,  # Smooth, steady learning
        'max_depth': 4,
        'min_child_weight': 100,  # Balanced node requirements
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'gamma': 0.1,
        'reg_alpha': 0.5,  # L1 Regularization to drop useless features
        'reg_lambda': 2.0,  # L2 Regularization
        'random_state': 42
    }

    logger.info("Starting Walk-Forward Validation (Fixed 200-Round Ensembles)...")

    auc_scores = []

    for w in windows:
        train_mask = (df['date'] >= w['train_start']) & (df['date'] <= w['train_end'])
        val_mask = (df['date'] >= w['val_start']) & (df['date'] <= w['val_end'])

        train_df = df[train_mask]
        val_df = df[val_mask]

        if len(train_df) == 0 or len(val_df) == 0:
            logger.warning(f"Window {w['window']} has empty sets. Skipping.")
            continue

        X_train, y_train = train_df[features], train_df['target']
        X_val, y_val = val_df[features], val_df['target']

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)

        # REMOVED early_stopping_rounds to force a full 200-tree ensemble
        model = xgb.train(
            params,
            dtrain,
            num_boost_round=200,
            verbose_eval=False
        )

        val_preds = model.predict(dval)
        auc = roc_auc_score(y_val, val_preds)
        trees = 200  # Fixed
        auc_scores.append(auc)

        logger.info(f"Window {w['window']:02d} | Trees: {trees:03d} | AUC: {auc:.4f}")

    avg_auc = sum(auc_scores) / len(auc_scores) if auc_scores else 0
    logger.info(f"Walk-Forward Complete. Average AUC: {avg_auc:.4f}")

    logger.info("Training final production model on ALL data...")
    X_all, y_all = df[features], df['target']
    dall = xgb.DMatrix(X_all, label=y_all)

    final_model = xgb.train(params, dall, num_boost_round=200)

    model_dir = BASE_DIR / "ml" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "signal_model.pkl"

    joblib.dump({'model': final_model, 'features': features}, model_path)
    logger.success(f"Production model saved to {model_path}")


if __name__ == "__main__":
    train_model()