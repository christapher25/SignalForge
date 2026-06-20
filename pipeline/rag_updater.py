import sys
from pathlib import Path
from loguru import logger
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from rag.chunker import chunk_text
from nlp.embedder import get_embeddings
from rag.chroma_store import add_documents


def update_rag_database(tickers: list[str]):
    logger.info("Initializing RAG Weekend News Updater...")

    api_key = getattr(config, 'ALPACA_API_KEY', None)
    secret_key = getattr(config, 'ALPACA_SECRET_KEY', None)

    if not api_key or not secret_key:
        logger.error("CRITICAL: Alpaca keys missing in config.py")
        return

    # Using raw_data=True bypasses Pydantic object attribute errors completely
    client = NewsClient(api_key, secret_key, raw_data=True)

    for ticker in tickers:
        logger.info(f"Fetching latest weekend news for {ticker}...")

        try:
            request_params = NewsRequest(symbols=ticker, limit=5)
            # Since raw_data=True, news_response is a guaranteed dictionary
            news_response = client.get_news(request_params)

            # Safely extract the news list
            news_list = news_response.get('news', []) if isinstance(news_response, dict) else []

            if not news_list:
                logger.warning(f"No recent news found for {ticker}.")
                continue

            documents = []
            metadatas = []
            ids = []

            for article in news_list:
                # Extract dictionary properties
                headline = article.get('headline', 'No Headline')
                summary = article.get('summary', '')
                created_at = article.get('created_at', '')
                source = article.get('source', 'Alpaca')
                article_id = article.get('id', 'unknown_id')

                full_text = f"HEADLINE: {headline}\nSUMMARY: {summary}"

                # Break text into 400-character chunks
                chunks = chunk_text(full_text, chunk_size=400, chunk_overlap=50)

                for i, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append({
                        "ticker": ticker,
                        "date": str(created_at)[:10],  # Extract YYYY-MM-DD safely
                        "source": source if source else "Alpaca"
                    })
                    ids.append(f"{ticker}_{article_id}_{i}")

            if documents:
                logger.info(f"Chunked into {len(documents)} segments. Generating GPU embeddings...")
                embeddings = get_embeddings(documents)

                logger.info("Injecting vectors into ChromaDB...")
                add_documents(
                    collection_name="sec_macro_news",
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )

        except Exception as e:
            logger.error(f"Failed to process news for {ticker}: {e}")

    logger.success("✅ RAG Vector Database successfully updated for the Monday open!")


if __name__ == "__main__":
    active_tickers = ["AAPL", "MSFT", "NVDA", "SPY"]
    update_rag_database(active_tickers)