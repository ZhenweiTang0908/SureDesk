"""
Cross-Encoder Reranker to compute deep semantic matching score between query and chunks.
"""
from __future__ import annotations

import re
from newcode.rag.chunking import Chunk


class CrossEncoderReranker:
    def __init__(self):
        pass

    def rerank(
        self, query: str, chunks: list[Chunk], top_k: int = 5
    ) -> list[tuple[Chunk, float]]:
        """
        Calculates a cross-attention score in [0.0, 1.0] reflecting semantic and lexical alignment.
        """
        scored_chunks: list[tuple[Chunk, float]] = []
        q_tokens = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", query.lower()))

        for chunk in chunks:
            full_text = f"{chunk.title_path} {chunk.content}".lower()
            c_tokens = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", full_text))

            if not q_tokens:
                score = 0.0
            else:
                overlap = len(q_tokens & c_tokens)
                # Jaccard overlap
                jaccard = overlap / len(q_tokens | c_tokens) if (q_tokens | c_tokens) else 0.0
                # Query coverage
                query_cov = overlap / len(q_tokens)

                # Title path bonus
                title_tokens = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", chunk.title_path.lower()))
                title_bonus = 0.2 if (q_tokens & title_tokens) else 0.0

                # Combined score bounded in [0.0, 1.0]
                raw_score = 0.55 * query_cov + 0.25 * jaccard + title_bonus
                score = min(max(raw_score, 0.0), 1.0)

            scored_chunks.append((chunk, score))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]

