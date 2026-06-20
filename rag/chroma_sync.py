# rag/chroma_sync.py
import os

os.environ["CHROMA_TELEMETRY_DISABLED"] = "1"  # Silence telemetry completely

import sys
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

import pandas as pd
from sqlalchemy import create_engine, text
from loguru import logger
import chromadb
from chromadb.config import Settings
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def get_recent_news_from_sqlite(engine, hours_back: int = 24) -> pd.DataFrame:
    """Extracts the freshest articles from the SQLite daemon's ingestion pool."""
    logger.info(f"Querying SQLite for news ingested in the last {hours_back} hours...")

    cutoff_date = (datetime.now() - timedelta(hours=hours_back)).date()

    query = text("""
        SELECT ticker, date, headline, full_text, uuid, finbert_sentiment 
        FROM news 
        WHERE date >= :cutoff_date
    """)

    try:
        df = pd.read_sql(query, engine, params={"cutoff_date": cutoff_date})
        logger.info(f"Retrieved {len(df)} active articles for vector embedding.")
        return df
    except Exception as e:
        logger.error(f"Failed to query SQLite news table: {e}")
        return pd.DataFrame()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def initialize_chromadb() -> chromadb.Collection:
    """Boots the local vector DB and targets the core financial collection."""
    chroma_dir = BASE_DIR / "rag" / "chroma_db"
    chroma_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Connecting to local ChromaDB instance...")
    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=Settings(anonymized_telemetry=False)
    )

    collection = client.get_or_create_collection(
        name="financial_news",
        metadata={"hnsw:space": "cosine"}
    )
    return collection


def sync_pipeline(hours_back: int = 24):
    """The master sync function to bridge SQLite and ChromaDB with strict null safety."""
    engine = create_engine(f"sqlite:///{config.DB_PATH}")

    # 1. Fetch raw data
    df = get_recent_news_from_sqlite(engine, hours_back)

    if df.empty:
        logger.warning("No new articles found in SQLite. Vector sync aborted.")
        return

    # 2. Boot Vector DB
    collection = initialize_chromadb()

    # 3. Prepare Embedding Payloads
    documents = []
    metadatas = []
    ids = []

    for idx, row in df.iterrows():
        # Fallback for UUID: If the record doesn't have a UUID, generate a stable one from the headline
        headline_text = row['headline'] if row['headline'] else f"Empty Headline {idx}"
        if row['uuid']:
            doc_id = str(row['uuid'])
        else:
            doc_id = hashlib.md5(f"{row['ticker']}_{headline_text}".encode('utf-8')).hexdigest()

        ids.append(doc_id)

        # Fallback for Sentiment: Default to 0.00 (Neutral) if FinBERT evaluation is missing
        sentiment_val = float(row['finbert_sentiment']) if row['finbert_sentiment'] is not None else 0.0
        full_story = row['full_text'] if row['full_text'] else "No summary content provided."

        composite_text = (
            f"Headline: {headline_text}. "
            f"Sentiment Score: {sentiment_val:.2f}. "
            f"Summary: {full_story}"
        )
        documents.append(composite_text)

        metadatas.append({
            "ticker": str(row['ticker']),
            "date": str(row['date'])
        })

    if not ids:
        return

    logger.info(f"Chunking and embedding {len(documents)} vectors. This will use the local runtime embedder...")

    # 4. Safe Batch Insertion via Upsert
    try:
        batch_size = 100
        total_synced = 0

        for i in range(0, len(ids), batch_size):
            collection.upsert(
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
                ids=ids[i:i + batch_size]
            )
            total_synced += len(ids[i:i + batch_size])
            logger.debug(f"Embedded batch {i // batch_size + 1}... ({total_synced}/{len(ids)})")

        logger.success(f"Vector Sync Complete: {total_synced} articles successfully parsed into ChromaDB.")

    except Exception as e:
        logger.error(f"Failed to upsert vectors into ChromaDB: {e}")


if __name__ == "__main__":
    logger.info("Initializing Daily SQLite-to-ChromaDB Sync Pipeline...")
    sync_pipeline(hours_back=48)