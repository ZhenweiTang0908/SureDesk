"""
Unified Hybrid Retrieval Engine combining Hierarchical Chunking, Dense, BM25, RRF, and Rerank.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from newcode.rag.chunking import Chunk, HierarchicalMarkdownChunker
from newcode.rag.bm25 import BM25Retriever
from newcode.rag.dense import DenseRetriever
from newcode.rag.fusion import rrf_fusion
from newcode.rag.reranker import CrossEncoderReranker


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    rrf_score: float
    dense_score: float
    bm25_score: float
    rerank_score: float


class HybridRetrievalEngine:
    def __init__(self):
        self.chunker = HierarchicalMarkdownChunker()
        self.dense_retriever = DenseRetriever()
        self.bm25_retriever = BM25Retriever()
        self.reranker = CrossEncoderReranker()
        self.chunks: list[Chunk] = []
        self.chunk_map: dict[str, Chunk] = {}

    def add_markdown_document(self, text: str, source_doc: str = "doc") -> list[Chunk]:
        new_chunks = self.chunker.chunk_document(text, source_doc=source_doc)
        self.chunks.extend(new_chunks)
        self.chunk_map.update({c.chunk_id: c for c in new_chunks})
        self.dense_retriever.index(self.chunks)
        self.bm25_retriever.index(self.chunks)
        return new_chunks

    def add_chunks(self, chunks: list[Chunk]) -> None:
        self.chunks.extend(chunks)
        self.chunk_map.update({c.chunk_id: c for c in chunks})
        self.dense_retriever.index(self.chunks)
        self.bm25_retriever.index(self.chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        dense_limit: int = 15,
        bm25_limit: int = 15,
        k_rrf: int = 60,
    ) -> list[ScoredChunk]:
        if not self.chunks:
            return []

        # 1. Dual-path retrieval
        dense_results = self.dense_retriever.retrieve(query, top_k=dense_limit)
        bm25_results = self.bm25_retriever.retrieve(query, top_k=bm25_limit)

        dense_scores_dict = dict(dense_results)
        bm25_scores_dict = dict(bm25_results)

        # 2. RRF Fusion
        rrf_results = rrf_fusion([dense_results, bm25_results], k=k_rrf, top_k=max(dense_limit, bm25_limit))
        rrf_scores_dict = dict(rrf_results)

        # 3. Candidate gathering for Rerank
        candidate_ids = [doc_id for doc_id, _ in rrf_results]
        candidate_chunks = [self.chunk_map[doc_id] for doc_id in candidate_ids if doc_id in self.chunk_map]

        # 4. Cross-Encoder Rerank
        reranked = self.reranker.rerank(query, candidate_chunks, top_k=top_k)

        # 5. Pack into ScoredChunk
        final_results: list[ScoredChunk] = []
        for chunk, rerank_score in reranked:
            final_results.append(
                ScoredChunk(
                    chunk=chunk,
                    score=rerank_score,
                    rrf_score=rrf_scores_dict.get(chunk.chunk_id, 0.0),
                    dense_score=dense_scores_dict.get(chunk.chunk_id, 0.0),
                    bm25_score=bm25_scores_dict.get(chunk.chunk_id, 0.0),
                    rerank_score=rerank_score,
                )
            )

        return final_results

