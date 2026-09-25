"""
Pre-generation Confidence Gate to guard against hallucinations and fake policy commitments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from newcode.rag.engine import ScoredChunk


@dataclass
class GateDecision:
    passed: bool
    confidence_score: float
    reason: str
    rejection_answer: str | None = None


class ConfidenceGate:
    """
    Evaluates evidence sufficiency before LLM generation.
    - If highest rerank score < threshold: REJECT with standard polite fallback.
    - If query asks about unknown policy: REJECT.
    """

    def __init__(self, score_threshold: float = 0.55):
        self.score_threshold = score_threshold

    def evaluate(self, query: str, scored_chunks: list[ScoredChunk]) -> GateDecision:
        if not scored_chunks:
            return GateDecision(
                passed=False,
                confidence_score=0.0,
                reason="未检索到任何相关知识库条目，置信度不足",
                rejection_answer=(
                    "非常抱歉，我们目前的客服知识库中暂未收录关于该问题的权威政策说明。"
                    "为了避免给您造成误导，我已自动将您的问题记录并流转至运营与专家知识库团队审核补全。"
                    "如有紧急需求，您可以直接转接人工客服协助处理。"
                ),
            )

        best_score = scored_chunks[0].score

        if best_score < self.score_threshold:
            return GateDecision(
                passed=False,
                confidence_score=best_score,
                reason=f"最高相关度得分 {best_score:.2f} 低于安全阈值 {self.score_threshold:.2f}，触发前置防幻觉拦截",
                rejection_answer=(
                    "抱歉，我未能找到完全符合您提问的官方政策依据。"
                    "为保障您的权益，暂无法为您确认该事项，该问题已自动沉淀到待审核问题池。"
                    "您可以尝试换一种提问方式，或回复“人工”为您转接人工客服。"
                ),
            )

        return GateDecision(
            passed=True,
            confidence_score=best_score,
            reason=f"证据充分，最高得分 {best_score:.2f} >= {self.score_threshold:.2f}，放行至生成节点",
        )

