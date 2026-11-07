"""LLM answer integration at the agent-node boundary."""

from __future__ import annotations

from types import SimpleNamespace

from newcode.rag.chunking import Chunk
from newcode.rag.engine import ScoredChunk
from newcode.schemas.intent import IntentType, RouteTarget
from newcode.workflow.nodes.agent_node import execute_agent_node
from newcode.workflow.state import CustomerServiceState


class FakeLLM:
    """Return a deterministic answer and record the prompt."""

    def __init__(self, answer: str = "AI answer") -> None:
        self.answer = answer
        self.messages: list[dict[str, str]] = []

    async def generate_text(self, messages, **kwargs):
        self.messages = messages
        return self.answer


def make_state(query: str, intent: IntentType, route: RouteTarget) -> CustomerServiceState:
    return CustomerServiceState(
        session_id="sess_test",
        user_id="user_test",
        query=query,
        rewritten_query=query,
        intent=intent,
        route=route,
    )


async def test_chitchat_uses_llm_when_available():
    llm = FakeLLM("你好，我是 SureDesk。")
    state = make_state("你好", IntentType.CHITCHAT, RouteTarget.FALLBACK_DIRECT)

    result = await execute_agent_node(state, llm_client=llm)

    assert result.final_answer == "你好，我是 SureDesk。"
    assert "customer service assistant" in llm.messages[0]["content"]


async def test_grounded_answer_uses_evidence_and_falls_back():
    chunk = Chunk(
        chunk_id="chunk_1",
        content="常规现货订单在付款成功后48小时内发货。",
        title_path="政策手册 > 发货承诺时效",
    )
    scored = ScoredChunk(
        chunk=chunk,
        score=0.9,
        rrf_score=0.9,
        dense_score=0.9,
        bm25_score=0.9,
        rerank_score=0.9,
    )
    engine = SimpleNamespace(retrieve=lambda query, top_k=3: [scored])

    llm = FakeLLM("常规订单会在付款后48小时内发货。")
    state = make_state("多久发货？", IntentType.PRE_SALE_RULES, RouteTarget.MAIN_AGENT_RAG)
    result = await execute_agent_node(state, rag_engine=engine, llm_client=llm)

    assert result.final_answer.startswith("常规订单会在付款后48小时内发货。")
    assert "依据政策来源" in result.final_answer
    assert "48小时内发货" in llm.messages[1]["content"]

    fallback_state = make_state("多久发货？", IntentType.PRE_SALE_RULES, RouteTarget.MAIN_AGENT_RAG)
    fallback = await execute_agent_node(
        fallback_state,
        rag_engine=engine,
        llm_client=FakeLLM(""),
    )

    assert fallback.final_answer.startswith(chunk.content)
    assert "依据政策来源" in fallback.final_answer

