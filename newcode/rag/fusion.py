"""
Reciprocal Rank Fusion (RRF) for combining multiple ranked retrieval candidate lists.
"""
from __future__ import annotations


def rrf_fusion(
    rank_lists: list[list[tuple[str, float]]],
    k: int = 60,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """
    RRF Formula: Score(doc) = sum_{list i} (1 / (k + rank_{i}(doc)))
    rank is 1-indexed.
    """
    scores: dict[str, float] = {}
    for rank_list in rank_lists:
        for rank, (doc_id, _) in enumerate(rank_list, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank))

    sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if top_k is not None:
        return sorted_results[:top_k]
    return sorted_results

