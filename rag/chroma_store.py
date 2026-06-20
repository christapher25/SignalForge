import sys
import chromadb
from pathlib import Path
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# We use a persistent local ChromaDB stored strictly in the db/ folder
CHROMA_PATH = BASE_DIR / "db" / "chroma"
CHROMA_PATH.mkdir(parents=True, exist_ok=True)

logger.info(f"Initializing ChromaDB at {CHROMA_PATH}")
client = chromadb.PersistentClient(path=str(CHROMA_PATH))

def get_collection(name="sec_macro_news"):
    return client.get_or_create_collection(name=name)

def add_documents(collection_name: str, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]):
    collection = get_collection(collection_name)
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )
    logger.success(f"Added {len(documents)} documents to Chroma collection '{collection_name}'")

def query_documents(collection_name: str, query_embedding: list[float], n_results: int = 3, where: dict = None) -> dict:
    collection = get_collection(collection_name)
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where
    )