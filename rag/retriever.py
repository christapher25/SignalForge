from nlp.embedder import get_embeddings
from rag.chroma_store import query_documents
from loguru import logger


def retrieve_context(query: str, ticker: str, top_k: int = 3) -> str:
    """
    Embeds the LLM's query and retrieves the most relevant chunks from ChromaDB.
    Strictly filters by ticker metadata to ensure zero cross-contamination.
    """
    logger.info(f"Retrieving SEC/News context for {ticker}...")

    try:
        query_emb = get_embeddings([query])[0]

        # Filter strictly by ticker
        results = query_documents(
            collection_name="sec_macro_news",
            query_embedding=query_emb,
            n_results=top_k,
            where={"ticker": ticker}
        )

        if not results['documents'] or not results['documents'][0]:
            return "No recent fundamental news or SEC filings found."

        context = "\n".join(results['documents'][0])
        logger.success(f"Retrieved {len(results['documents'][0])} context chunks for {ticker}.")
        return context

    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return "Context retrieval unavailable."