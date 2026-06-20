import sys
import requests
import json
from pathlib import Path
from loguru import logger

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rag.retriever import retrieve_context

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:1b"


def generate_explanation(signal_data: dict) -> str:
    logger.info(f"Generating local explanation via Ollama ({MODEL_NAME}) with RAG...")

    ticker = signal_data.get('ticker', 'UNKNOWN')
    action = signal_data.get('action', 'HOLD')
    price = signal_data.get('entry_price', 0.0)

    # 1. Retrieve Fundamental Context (RAG)
    query = f"Recent news, macro events, and SEC filings for {ticker}."
    try:
        context = retrieve_context(query=query, ticker=ticker, top_k=2)
    except Exception as e:
        logger.warning(f"RAG retrieval failed for {ticker}, defaulting to empty context: {e}")
        context = ""

    # --- CONTEXT-STARVATION GUARDRAIL ---
    # If the context is completely empty or just whitespace, short-circuit immediately.
    # This completely eliminates 1B model hallucinations and drops execution latency to 0ms.
    if not context or not context.strip():
        logger.info(f"Zero fundamental news found for {ticker}. Applying structural fallback.")
        return "No recent fundamental catalysts or breaking news items detected. This trade setup is driven entirely by technical trend structure and quantitative velocity indicators."

    # 2. Build the Clean Augmented Prompt (Cleaned of all backend machine learning keywords)
    prompt = (
        f"You are a professional financial market news analyst. A quantitative trading model has flagged a "
        f"new structural {action} setup for {ticker} at a reference price of ${price:.2f}.\n\n"
        f"Recent Breaking News & Context:\n{context}\n\n"
        f"Task:\n"
        f"Write a clean, objective 2-to-3 sentence commentary explaining how the recent breaking news updates or "
        f"fundamental milestones support or impact this {action} outlook. "
        f"Strict Constraints:\n"
        f"- Focus entirely on real-world events, earnings, or corporate metrics provided in the text above.\n"
        f"- NEVER mention backend terms like 'XGBoost', 'model', 'confidence', 'probability', 'algorithm', or 'dataset'.\n"
        f"- Do not state or replicate prompt artifacts or random number fractions.\n"
        f"- Do not offer explicit financial recommendations or advice. Keep the delivery concise, crisp, and analytical."
    )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Kept very low to force strict compliance to the text context
            "top_p": 0.9
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=45)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama request failed: {e}")
        raise e