import sys
from pathlib import Path

# Fix paths so imports work
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rag.retriever import retrieve_context

ticker = "AAPL"  # Change this to any ticker you want to test
print(f"--- Querying Vector Database for {ticker} ---")

try:
    context = retrieve_context(query=f"Recent news and events for {ticker}", ticker=ticker, top_k=2)

    if not context or not context.strip():
        print("❌ FAILED: The RAG returned an empty string. The news did not sync to ChromaDB.")
    else:
        print("✅ SUCCESS: The RAG returned the following context for the LLM to read:\n")
        print(context)

except Exception as e:
    print(f"❌ ERROR: RAG pipeline crashed: {e}")