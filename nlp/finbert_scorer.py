import sys
import json
import torch
import warnings
from pathlib import Path
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text
from tqdm import tqdm
from tenacity import retry, wait_exponential, stop_after_attempt
from transformers import pipeline

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def load_finbert_pipeline():
    logger.debug("Loading ProsusAI/finbert pipeline...")
    device = 0 if torch.cuda.is_available() else -1
    pipe = pipeline("text-classification", model="ProsusAI/finbert", device=device, batch_size=64)
    logger.info(f"FinBERT loaded on device {device} (0=CUDA, -1=CPU)")
    return pipe


def get_weighted_score(label: str, score: float) -> float:
    label = label.lower()
    if label == 'positive':
        return float(score * 1.0)
    elif label == 'negative':
        return float(score * -1.0)
    return 0.0


def run_finbert_scoring():
    logger.debug("Starting FinBERT scoring pipeline...")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = config.PROCESSED_DIR / 'finbert_checkpoint.json'

    pipe = load_finbert_pipeline()

    try:
        with engine.connect() as conn:
            query = text("""
                SELECT rowid as id, headline, full_text 
                FROM news 
                WHERE finbert_sentiment IS NULL OR finbert_sentiment = 0.0
            """)
            df = pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Database read failed: {e}")
        sys.exit(1)

    if df.empty:
        logger.info("No rows pending FinBERT scoring.")
        return

    processed_ids = set()
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, 'r') as f:
                processed_ids = set(json.load(f))
            logger.info(f"Loaded checkpoint: {len(processed_ids)} rows already processed.")
        except Exception:
            pass

    df_pending = df[~df['id'].isin(processed_ids)].copy()

    # Pre-concatenate text for processing
    df_pending['combined_text'] = df_pending['headline'].fillna('') + ". " + df_pending['full_text'].fillna('')
    # Truncate string to avoid huggingface excessive token warnings
    df_pending['combined_text'] = df_pending['combined_text'].str.slice(0, 512)

    logger.info(f"Processing {len(df_pending)} rows...")

    chunk_size = 1000
    batches_run = 0

    for start_idx in tqdm(range(0, len(df_pending), chunk_size), desc="FinBERT 1k Chunks"):
        chunk = df_pending.iloc[start_idx:start_idx + chunk_size]
        texts = chunk['combined_text'].tolist()
        row_ids = chunk['id'].tolist()

        try:
            # Pipeline processes efficiently with the built-in batch_size=64
            results = pipe(texts, truncation=True, max_length=512)

            updates = []
            for i, res in enumerate(results):
                weighted_val = get_weighted_score(res['label'], res['score'])
                updates.append({
                    "f": weighted_val,
                    "rid": int(row_ids[i])
                })

            batches_run += (len(texts) // 64) + 1
            if torch.cuda.is_available() and batches_run % 500 == 0:
                mem_gb = torch.cuda.memory_allocated(0) / (1024 ** 3)
                logger.info(f"GPU Memory Allocated: {mem_gb:.2f} GB")

            with engine.begin() as conn:
                stmt = text("UPDATE news SET finbert_sentiment = :f WHERE rowid = :rid")
                result = conn.execute(stmt, updates)
                if result.rowcount < len(updates):
                    logger.error(f"Silent write failure: Expected {len(updates)} updates, got {result.rowcount}")

            processed_ids.update(row_ids)
            with open(checkpoint_file, 'w') as f:
                json.dump(list(processed_ids), f)

        except Exception as e:
            logger.exception(f"Error processing FinBERT chunk starting at {start_idx}: {e}")
            continue

    logger.info("FinBERT pipeline completed successfully.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    run_finbert_scoring()