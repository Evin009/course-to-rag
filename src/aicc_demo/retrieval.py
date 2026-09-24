import numpy as np
from sentence_transformers import SentenceTransformer

from aicc_demo.assembly import Chunk


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class Retriever:
    def __init__(self, chunks: list[Chunk], model_name: str = "all-MiniLM-L6-v2"):
        self.chunks = chunks
        self.model = SentenceTransformer(model_name)
        self.embeddings = self.model.encode([c.text for c in chunks])

    def query(self, question: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        query_vec = self.model.encode([question])[0]
        scored = [
            (chunk, _cosine_similarity(query_vec, emb))
            for chunk, emb in zip(self.chunks, self.embeddings)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
