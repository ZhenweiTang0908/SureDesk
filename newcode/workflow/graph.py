"""
Overall LangGraph Workflow Orchestrator.
"""
from __future__ import annotations

from newcode.core.tracing import RequestTracer
from newcode.rag.engine import HybridRetrievalEngine
from newcode.services.memory import DualLayerMemoryManager
from newcode.services.problem_pool import ProblemPoolService
from newcode.services.router import ContextQueryRewriterAndRouter
from newcode.tools.registry import ToolRegistry
from newcode.workflow.nodes.agent_node import execute_agent_node
from newcode.workflow.nodes.refund_workflow import execute_refund_workflow
from newcode.workflow.state import CustomerServiceState


class CustomerServiceWorkflow:
    def __init__(
        self,
        rag_engine: HybridRetrievalEngine | None = None,
        tool_registry: ToolRegistry | None = None,
        problem_pool_service: ProblemPoolService | None = None,
    ):
        self.router = ContextQueryRewriterAndRouter()
        self.rag_engine = rag_engine or HybridRetrievalEngine()
        self.tool_registry = tool_registry or ToolRegistry()
        self.problem_pool_service = problem_pool_service or ProblemPoolService()
        self.memory = DualLayerMemoryManager()
        self.sessions: dict[tuple[str, str], CustomerServiceState] = {}

    async def run(
        self,
        user_id: str,
        session_id: str,
        query: str,
        history: list[dict[str, str]] | None = None,
    ) -> CustomerServiceState:
        tracer = RequestTracer(user_id=user_id, session_id=session_id)
        session_key = (user_id, session_id)

        # Session state is scoped to the authenticated user to prevent cross-user resume.
        prior_state = self.sessions.get(session_key)
        if prior_state and prior_state.is_suspended and prior_state.refund_status == "PENDING_ORDER_ID":
            span = tracer.start_span("refund_resume")
            prior_state.query = query
            prior_state.rewritten_query = query
            resumed_state = await execute_refund_workflow(prior_state)
            span.finish(refund_status=resumed_state.refund_status)
            self.sessions[session_key] = resumed_state
            await tracer.persist_audit()
            return resumed_state

        route_span = tracer.start_span("rewrite_and_route")
        prior_messages = list(history or [])
        if prior_state:
            prior_messages = [*prior_state.messages, {"role": "user", "content": prior_state.query}]
            if prior_state.final_answer:
                prior_messages.append({"role": "assistant", "content": prior_state.final_answer})
        memory_context = self.memory.process_messages(prior_messages)
        route_res = self.router.rewrite_and_route(query, history=memory_context.near_messages)
        route_span.finish(intent=route_res.intent.value, route=route_res.route.value)

        state = CustomerServiceState(
            session_id=session_id,
            user_id=user_id,
            query=query,
            rewritten_query=route_res.rewritten_query,
            intent=route_res.intent,
            route=route_res.route,
            confidence_score=route_res.confidence,
            messages=memory_context.near_messages,
        )

        # 2. Branch according to Route Target
        if route_res.route.value == "DETERMINISTIC_WORKFLOW":
            state = await execute_refund_workflow(state)
        elif route_res.route.value == "CLARIFY_PROMPT":
            state.is_suspended = True
            state.final_answer = "请问您具体想咨询哪款商品或哪个订单的信息呢？您可以提供商品名称或订单号以便我为您精准查询。"
            state.thoughts.append("信息缺失追问出口：向买家发起精准槽位追问。")
        else:
            execution_span = tracer.start_span("agent_execution")
            state = await execute_agent_node(
                state,
                rag_engine=self.rag_engine,
                tool_registry=self.tool_registry,
                problem_pool_service=self.problem_pool_service,
            )
            execution_span.finish(confidence=state.confidence_score)

        tracer.record_evidence(state.retrieved_chunks)
        self.sessions[session_key] = state
        await tracer.persist_audit()
        return state
