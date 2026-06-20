import json
import sys
from pathlib import Path
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
import config


def generate_windows():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    logger.info("Fetching date ranges from feature_matrix...")

    # Get unique dates and standardize to string format (YYYY-MM-DD)
    query = "SELECT DISTINCT date FROM feature_matrix ORDER BY date"
    dates = pd.read_sql(query, engine)['date'].astype(str).str[:10].tolist()

    if not dates:
        logger.error("No dates found in feature_matrix.")
        sys.exit(1)

    n_splits = 15
    total_days = len(dates)
    val_size = total_days // (n_splits + 2)

    windows = []
    for i in range(n_splits):
        train_start = dates[0]
        train_end = dates[(i + 2) * val_size]
        val_start = dates[(i + 2) * val_size + 1]
        val_end = dates[min((i + 3) * val_size, total_days - 1)]

        windows.append({
            "window": i + 1,
            "train_start": train_start,
            "train_end": train_end,
            "val_start": val_start,
            "val_end": val_end
        })

    window_path = BASE_DIR / "ml" / "windows.json"
    with open(window_path, "w") as f:
        json.dump(windows, f, indent=4)

    logger.success(f"Generated {n_splits} walk-forward windows. Saved to {window_path}")


if __name__ == "__main__":
    generate_windows()