"""
Problem Pool Service for Data Flywheel.
Supports 3 entrance triggers:
1. CONFIDENCE_GATE: Gate intercepted queries
2. SELF_EVAL_FAIL: Post-generation evaluation failed
3. USER_THUMBS_DOWN: User negative feedback
Includes text similarity deduplication and frequency merging.
"""
from __future__ import annotations

import re
from typing import Any
from sqlalchemy import select
from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import ProblemPool, TriggerType, OperatorStatus


def compute_text_similarity(s1: str, s2: str) -> float:
    """Computes character token Jaccard similarity between two queries."""
    s1, s2 = s1.strip().lower(), s2.strip().lower()
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    def get_chars(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text))

    c1, c2 = get_chars(s1), get_chars(s2)
    intersection = len(c1 & c2)
    union = len(c1 | c2)
    return intersection / union if union > 0 else 0.0


class ProblemPoolService:
    def __init__(self, similarity_threshold: float = 0.65):
        self.similarity_threshold = similarity_threshold

    async def add_or_merge_problem(
        self,
        session_id: str,
        trigger_type: TriggerType | str,
        query: str,
        rewritten_query: str = "",
        retrieved_chunks: list[dict[str, Any]] | None = None,
        answer: str = "",
    ) -> ProblemPool:
        trigger_val = (
            trigger_type.value
            if hasattr(trigger_type, "value")
            else str(trigger_type)
        )
        check_query = rewritten_query or query

        async with AsyncSessionLocal() as session:
            stmt = select(ProblemPool).where(ProblemPool.operator_status == OperatorStatus.PENDING.value)
            result = await session.execute(stmt)
            existing_list = result.scalars().all()

            for item in existing_list:
                existing_text = item.rewritten_query or item.query
                sim = compute_text_similarity(check_query, existing_text)
                if sim >= self.similarity_threshold:
                    item.frequency = (item.frequency or 1) + 1
                    current_sessions = list(item.sessions) if item.sessions else []
                    if session_id not in current_sessions:
                        current_sessions.append(session_id)
                    item.sessions = current_sessions
                    await session.commit()
                    await session.refresh(item)
                    return item

            new_item = ProblemPool(
                session_id=session_id,
                trigger_type=trigger_val,
                query=query,
                rewritten_query=rewritten_query or query,
                retrieved_chunks=retrieved_chunks or [],
                answer=answer,
                operator_status=OperatorStatus.PENDING.value,
                frequency=1,
                sessions=[session_id],
            )
            session.add(new_item)
            await session.commit()
            await session.refresh(new_item)
            return new_item

    async def get_pending_problems(self) -> list[ProblemPool]:
        async with AsyncSessionLocal() as session:
            stmt = select(ProblemPool).where(ProblemPool.operator_status == OperatorStatus.PENDING.value)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def adopt_and_sync(
        self, problem_id: str, standard_answer: str, rag_engine=None
    ) -> ProblemPool | None:
        async with AsyncSessionLocal() as session:
            stmt = select(ProblemPool).where(ProblemPool.id == problem_id)
            result = await session.execute(stmt)
            item = result.scalar_one_or_none()
            if not item:
                return None

            item.operator_status = OperatorStatus.ACCEPTED.value
            item.standard_answer = standard_answer
            await session.commit()
            await session.refresh(item)

            if rag_engine:
                doc_text = f"## 常见问题与官方解答\n\n### {item.rewritten_query or item.query}\n{standard_answer}"
                rag_engine.add_markdown_document(doc_text, source_doc=f"运营补全-问题{item.id}")

            return item

