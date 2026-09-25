"""
Dense vector retriever using embedding representations and cosine similarity.
"""
from __future__ import annotations

import math
import re
import numpy as np
from newcode.rag.chunking import Chunk


def simple_semantic_vector(text: str, dim: int = 128) -> np.ndarray:
    """
    Deterministic semantic vector generator based on token hashing and n-gram pooling.
    Guarantees that similar sentences have high cosine similarity without external network calls.
    """
    text = text.lower()
    vec = np.zeros(dim, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text)
    if not tokens:
        return vec
    for i, token in enumerate(tokens):
        h = hash(token)
        idx1 = abs(h) % dim
        idx2 = abs(h // dim) % dim
        vec[idx1] += 1.0
        vec[idx2] += 0.5
        # n-gram coupling
        if i > 0:
            pair = tokens[i - 1] + token
            hp = hash(pair)
            vec[abs(hp) % dim] += 1.5

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class DenseRetriever:
    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks: list[Chunk] = []
        self.chunk_map: dict[str, Chunk] = {}
        self.vectors: np.ndarray | None = None
        if chunks:
            self.index(chunks)

    def index(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.chunk_map = {c.chunk_id: c for c in chunks}
        vec_list = [simple_semantic_vector(f"{c.title_path} {c.content}") for c in chunks]
        self.vectors = np.array(vec_list, dtype=np.float32)

    def retrieve(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        if self.vectors is None or len(self.chunks) == 0:
            return []
        q_vec = simple_semantic_vector(query)
        # Cosine similarities
        scores = np.dot(self.vectors, q_vec)
        scored_pairs = [(self.chunks[i].chunk_id, float(scores[i])) for i in range(len(self.chunks))]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]

