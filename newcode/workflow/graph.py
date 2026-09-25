"""
Overall LangGraph Workflow Orchestrator.
"""
from __future__ import annotations

from newcode.services.router import ContextQueryRewriterAndRouter
from newcode.rag.engine import HybridRetrievalEngine
from newcode.tools.registry import ToolRegistry
from newcode.workflow.state import CustomerServiceState
from newcode.workflow.nodes.refund_workflow import execute_refund_workflow
from newcode.workflow.nodes.agent_node import execute_agent_node


class CustomerServiceWorkflow:
    def __init__(
        self,
        rag_engine: HybridRetrievalEngine | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.router = ContextQueryRewriterAndRouter()
        self.rag_engine = rag_engine or HybridRetrievalEngine()
        self.tool_registry = tool_registry or ToolRegistry()
        self.sessions: dict[str, CustomerServiceState] = {}

    async def run(
        self,
        user_id: str,
        session_id: str,
        query: str,
        history: list[dict[str, str]] | None = None,
    ) -> CustomerServiceState:
        # Check if existing session was suspended waiting for input
        prior_state = self.sessions.get(session_id)
        if prior_state and prior_state.is_suspended and prior_state.refund_status == "PENDING_ORDER_ID":
            # Resume refund workflow with newly provided query (expected order_id)
            prior_state.query = query
            prior_state.rewritten_query = query
            resumed_state = await execute_refund_workflow(prior_state)
            self.sessions[session_id] = resumed_state
            return resumed_state

        # 1. Query Rewrite and Intent Routing
        route_res = self.router.rewrite_and_route(query, history=history)

        state = CustomerServiceState(
            session_id=session_id,
            user_id=user_id,
            query=query,
            rewritten_query=route_res.rewritten_query,
            intent=route_res.intent,
            route=route_res.route,
            confidence_score=route_res.confidence,
            messages=history or [],
        )

        # 2. Branch according to Route Target
        if route_res.route.value == "DETERMINISTIC_WORKFLOW":
            state = await execute_refund_workflow(state)
        elif route_res.route.value == "CLARIFY_PROMPT":
            state.is_suspended = True
            state.final_answer = "请问您具体想咨询哪款商品或哪个订单的信息呢？您可以提供商品名称或订单号以便我为您精准查询。"
            state.thoughts.append("信息缺失追问出口：向买家发起精准槽位追问。")
        else:
            state = await execute_agent_node(state, rag_engine=self.rag_engine, tool_registry=self.tool_registry)

        self.sessions[session_id] = state
        return state

