"""
RAG Evaluator to compute Recall@K and MRR (Mean Reciprocal Rank) metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from newcode.rag.engine import HybridRetrievalEngine, ScoredChunk


@dataclass
class EvalResult:
    query_id: str
    query: str
    category: str
    expected_title: str
    hit_at_k: bool
    rank: int  # 1-based, 0 if not found
    reciprocal_rank: float
    retrieved_titles: list[str]


@dataclass
class SummaryMetrics:
    total_queries: int
    recall_at_k: float
    mrr: float
    results: list[EvalResult]


class RAGEvaluator:
    def __init__(self, engine: HybridRetrievalEngine):
        self.engine = engine

    def evaluate_query(
        self,
        query_id: str,
        query: str,
        expected_title: str,
        category: str,
        k: int = 5,
        mode: str = "hybrid",
    ) -> EvalResult:
        if mode == "dense":
            raw_hits = self.engine.dense_retriever.retrieve(query, top_k=k)
            retrieved = [self.engine.chunk_map[c_id] for c_id, _ in raw_hits if c_id in self.engine.chunk_map]
            titles = [c.title_path for c in retrieved]
        elif mode == "bm25":
            raw_hits = self.engine.bm25_retriever.retrieve(query, top_k=k)
            retrieved = [self.engine.chunk_map[c_id] for c_id, _ in raw_hits if c_id in self.engine.chunk_map]
            titles = [c.title_path for c in retrieved]
        else:  # hybrid
            scored_chunks = self.engine.retrieve(query, top_k=k)
            titles = [sc.chunk.title_path for sc in scored_chunks]

        # Determine rank
        found_rank = 0
        for idx, title_path in enumerate(titles, start=1):
            if expected_title in title_path:
                found_rank = idx
                break

        hit = 1 <= found_rank <= k
        rr = 1.0 / found_rank if hit else 0.0

        return EvalResult(
            query_id=query_id,
            query=query,
            category=category,
            expected_title=expected_title,
            hit_at_k=hit,
            rank=found_rank,
            reciprocal_rank=rr,
            retrieved_titles=titles,
        )

    def evaluate_benchmark(
        self,
        queries: list[dict[str, Any]],
        k: int = 5,
        mode: str = "hybrid",
    ) -> SummaryMetrics:
        results: list[EvalResult] = []
        for q in queries:
            res = self.evaluate_query(
                query_id=q["id"],
                query=q["query"],
                expected_title=q["expected_title"],
                category=q.get("category", "default"),
                k=k,
                mode=mode,
            )
            results.append(res)

        total = len(results)
        if total == 0:
            return SummaryMetrics(0, 0.0, 0.0, [])

        hits = sum(1 for r in results if r.hit_at_k)
        recall = hits / total
        mrr = sum(r.reciprocal_rank for r in results) / total

        return SummaryMetrics(total_queries=total, recall_at_k=recall, mrr=mrr, results=results)

