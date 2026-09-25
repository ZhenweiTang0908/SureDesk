"""
BM25 sparse retriever for Chinese and mixed language.
"""
from __future__ import annotations

import re
from rank_bm25 import BM25Okapi
from newcode.rag.chunking import Chunk


def tokenize(text: str) -> list[str]:
    """
    Robust tokenizer for Chinese, English, and numbers.
    Splits into Chinese characters, English words, numbers, and bi-grams.
    """
    text = text.lower()
    # Chinese characters
    tokens: list[str] = []
    # Match english words/numbers or individual chinese chars
    items = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text)
    tokens.extend(items)
    # Add character bi-grams for Chinese to enhance phrase recall
    chinese_chars = [c for c in items if re.match(r"[\u4e00-\u9fff]", c)]
    for i in range(len(chinese_chars) - 1):
        tokens.append(chinese_chars[i] + chinese_chars[i + 1])
    return tokens if tokens else [""]


class BM25Retriever:
    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks: list[Chunk] = []
        self.chunk_map: dict[str, Chunk] = {}
        self.bm25: BM25Okapi | None = None
        if chunks:
            self.index(chunks)

    def index(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.chunk_map = {c.chunk_id: c for c in chunks}
        corpus = [tokenize(f"{c.title_path} {c.content}") for c in chunks]
        self.bm25 = BM25Okapi(corpus)

    def retrieve(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        if not self.bm25 or not self.chunks:
            return []
        tokenized_query = tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        scored_pairs = [(self.chunks[i].chunk_id, float(scores[i])) for i in range(len(self.chunks))]
        # Sort descending by score
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]

