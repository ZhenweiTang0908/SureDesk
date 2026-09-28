"""Shared application services used by HTTP routes and workflow execution."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import OperatorStatus, ProblemPool
from newcode.rag.engine import HybridRetrievalEngine
from newcode.services.problem_pool import ProblemPoolService
from newcode.tools.logistics_tools import QueryLogisticsTool
from newcode.tools.order_tools import ListOrdersTool, QueryOrderTool
from newcode.tools.registry import ToolRegistry
from newcode.workflow.graph import CustomerServiceWorkflow


class ApplicationServices:
    """Own the process-wide retrieval index and workflow dependencies."""

    def __init__(self) -> None:
        self.rag_engine = HybridRetrievalEngine()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(QueryOrderTool())
        self.tool_registry.register(ListOrdersTool())
        self.tool_registry.register(QueryLogisticsTool())
        self.problem_pool = ProblemPoolService()
        self.workflow = CustomerServiceWorkflow(
            rag_engine=self.rag_engine,
            tool_registry=self.tool_registry,
            problem_pool_service=self.problem_pool,
        )
        self._initialized = False
        self._initialization_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Load bundled and operator-approved knowledge into the shared index once."""
        if self._initialized:
            return
        async with self._initialization_lock:
            if self._initialized:
                return

            knowledge_path = Path(__file__).resolve().parents[2] / "knowledge_base" / "ecommerce_faq.md"
            if knowledge_path.exists():
                self.rag_engine.add_markdown_document(
                    knowledge_path.read_text(encoding="utf-8"),
                    source_doc="ecommerce_faq.md",
                )

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ProblemPool).where(
                        ProblemPool.operator_status == OperatorStatus.ACCEPTED.value,
                        ProblemPool.standard_answer.is_not(None),
                    )
                )
                for item in result.scalars():
                    self._index_adopted_problem(item)

            self._initialized = True

    def _index_adopted_problem(self, item: ProblemPool) -> None:
        question = item.rewritten_query or item.query
        answer = item.standard_answer or ""
        if not answer.strip():
            return
        self.rag_engine.add_markdown_document(
            f"## Operator-approved answer\n\n### {question}\n{answer}",
            source_doc=f"operator-answer-{item.id}",
        )


application_services = ApplicationServices()
