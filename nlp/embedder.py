import torch
from sentence_transformers import SentenceTransformer
from loguru import logger

# INVARIANT ENFORCEMENT: MiniLM strictly on CUDA (GPU)
device = 'cuda' if torch.cuda.is_available() else 'cpu'
if device == 'cpu':
    logger.warning("CUDA not detected. MiniLM will run on CPU, violating architecture.")

logger.info(f"Loading MiniLM embedding model on {device}...")
model = SentenceTransformer('all-MiniLM-L6-v2', device=device)

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Generates vector embeddings for a list of text chunks."""
    if not texts:
        return []
    embeddings = model.encode(texts, convert_to_numpy=True).tolist()
    return embeddings