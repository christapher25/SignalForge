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
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
import config


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def load_finbert():
    logger.debug("Loading FinBERT model and tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    logger.info(f"FinBERT loaded successfully on {device}")
    return tokenizer, model, device


def analyze_vader(text_input, analyzer):
    try:
        scores = analyzer.polarity_scores(str(text_input))
        return scores['compound']
    except Exception as e:
        logger.error(f"VADER analysis failed: {e}")
        return 0.0


def analyze_finbert(text_input, tokenizer, model, device):
    try:
        inputs = tokenizer(str(text_input), return_tensors="pt", truncation=True, max_length=512, padding=True).to(
            device)
        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
            pos = probs[0][0].item()
            neg = probs[0][1].item()
            return pos - neg
    except Exception as e:
        logger.error(f"FinBERT analysis failed (likely length/OOM): {e}")
        return None


def process_sentiment():
    logger.debug("Starting process_sentiment()")
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = config.PROCESSED_DIR / 'sentiment_checkpoint.json'

    tokenizer, model, device = load_finbert()
    vader_analyzer = SentimentIntensityAnalyzer()

    try:
        with engine.connect() as conn:
            # Explicit aliasing to prevent Pandas from dropping the SQLite rowid
            query = text(
                "SELECT rowid AS id, ticker, full_text, vader_sentiment, finbert_sentiment FROM news WHERE vader_sentiment IS NULL OR finbert_sentiment IS NULL")
            df = pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Failed to fetch pending news rows: {e}")
        sys.exit(1)

    if df.empty:
        logger.info("No pending rows require sentiment analysis.")
        return

    logger.info(f"Found {len(df)} rows pending sentiment analysis.")

    processed_ids = set()
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, 'r') as f:
                processed_ids = set(json.load(f))
            logger.info(f"Loaded checkpoint: {len(processed_ids)} rows already processed.")
        except Exception as e:
            logger.error(f"Failed to load checkpoint file: {e}")

    df_pending = df[~df['id'].isin(processed_ids)].copy()
    logger.info(f"Processing {len(df_pending)} rows in batches of 50...")

    for i in tqdm(range(0, len(df_pending), 50), desc="Sentiment Batches"):
        batch = df_pending.iloc[i:i + 50]
        updates = []
        successful_ids = []

        for _, row in batch.iterrows():
            row_id = row['id']
            txt = row['full_text']

            v_sent = row['vader_sentiment']
            if pd.isna(v_sent):
                v_sent = analyze_vader(txt, vader_analyzer)

            f_sent = row['finbert_sentiment']
            s_method = 'vader+finbert'

            if pd.isna(f_sent):
                f_sent = analyze_finbert(txt, tokenizer, model, device)
                if f_sent is None:
                    f_sent = v_sent
                    s_method = 'vader_fallback'

            updates.append({
                "v": float(v_sent),
                "f": float(f_sent),
                "m": s_method,
                "rid": int(row_id)
            })
            successful_ids.append(int(row_id))

        if updates:
            try:
                with engine.begin() as conn:
                    stmt = text("""
                        UPDATE news 
                        SET vader_sentiment = :v, finbert_sentiment = :f, sentiment_method = :m 
                        WHERE rowid = :rid
                    """)
                    result = conn.execute(stmt, updates)

                    if result.rowcount < len(updates):
                        logger.error(
                            f"Database write partially failed. Expected {len(updates)} updates, got {result.rowcount}.")
                    else:
                        logger.debug(f"Successfully updated {result.rowcount} rows in DB.")
            except Exception as e:
                logger.error(f"Database transaction failed for batch {i}: {e}")
                continue

        processed_ids.update(successful_ids)
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(list(processed_ids), f)
        except Exception as e:
            logger.error(f"Failed to write checkpoint file: {e}")

    logger.info("process_sentiment() completed successfully.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    process_sentiment()