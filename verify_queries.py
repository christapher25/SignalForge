import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
import config


def verify():
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    try:
        macro_count = pd.read_sql("SELECT COUNT(*) FROM macro", engine).iloc[0, 0]
        print(f"Macro Rows (>5000): {macro_count}")
    except Exception as e:
        print(f"Macro Rows: ERROR - {e}")

    try:
        news_count = pd.read_sql("SELECT COUNT(*) FROM news WHERE finbert_sentiment IS NULL", engine).iloc[0, 0]
        print(f"News Unscored (0): {news_count}")
    except Exception as e:
        print(f"News Unscored: ERROR - {e}")

    try:
        ind_count = pd.read_sql("SELECT COUNT(DISTINCT ticker) FROM indicators", engine).iloc[0, 0]
        print(f"Indicators Tickers (>=750): {ind_count}")
    except Exception as e:
        print(f"Indicators Tickers: ERROR - {e}")


if __name__ == "__main__":
    verify()