"""
Main ReAct Agent Node integrating Knowledge Retrieval, Tool Calling, and Direct Fallback.
"""
from __future__ import annotations

import re

from newcode.guard.confidence_gate import ConfidenceGate
from newcode.models.domain import TriggerType
from newcode.rag.engine import HybridRetrievalEngine
from newcode.schemas.intent import IntentType, RouteTarget
from newcode.services.problem_pool import ProblemPoolService
from newcode.tools.base import SecurityContext
from newcode.tools.registry import ToolRegistry
from newcode.workflow.state import CustomerServiceState


async def execute_agent_node(
    state: CustomerServiceState,
    rag_engine: HybridRetrievalEngine | None = None,
    tool_registry: ToolRegistry | None = None,
    problem_pool_service: ProblemPoolService | None = None,
    confidence_gate: ConfidenceGate | None = None,
) -> CustomerServiceState:
    """
    Executes Main Agent flow:
    - If route is FALLBACK_DIRECT: handle chitchat or safety directly.
    - If route is TRANSFER_HUMAN: output transfer message.
    - If route is MAIN_AGENT_RAG: retrieve knowledge base or call tools.
    """
    route = state.route
    query = state.rewritten_query or state.query

    # 1. Fallback Direct (Chitchat or Safety)
    if route == RouteTarget.FALLBACK_DIRECT:
        if state.intent == IntentType.SENSITIVE_VIOLATION:
            state.final_answer = "您的输入涉及平台禁止的违规违禁内容，已被系统安全机制拦截并记录。"
            state.thoughts.append("安全防御：触发敏感违规前置拦截。")
            return state
        else:
            state.final_answer = "您好！我是 SureDesk 智能客服助手，请问有什么可以帮您的？支持查询订单、追踪物流、退换货以及政策咨询。"
            state.thoughts.append("闲聊出口：输出标准亲切问候语。")
            return state

    # 2. Transfer Human
    if route == RouteTarget.TRANSFER_HUMAN:
        ticket_id = f"TICKET-2026-{state.user_id[-4:]}-01"
        state.final_answer = (
            f"非常抱歉给您带来不好的体验！已为您优先接入专属人工客服通道，正在排队转接中..."
            f"若当前处于非人工在线时段，系统已为您创建高优先级加急工单（工单号：{ticket_id}），客诉专员将在2小时内与您电话联系。"
        )
        state.thoughts.append("转人工出口：已创建客诉加急工单并触发通道转接。")
        return state

    # 3. Execute authenticated order and logistics tools before knowledge retrieval.
    if tool_registry and state.intent in (IntentType.ORDER_QUERY, IntentType.LOGISTICS_PROGRESS):
        context = SecurityContext(user_id=state.user_id, session_id=state.session_id)
        order_match = re.search(r"ord_[a-zA-Z0-9_]+", query)
        if state.intent == IntentType.LOGISTICS_PROGRESS and not order_match:
            state.is_suspended = True
            state.final_answer = "请提供需要查询物流的订单号，例如 ord_1001。"
            return state

        tool_name = "query_logistics" if state.intent == IntentType.LOGISTICS_PROGRESS else (
            "query_order" if order_match else "list_user_orders"
        )
        params = {"order_id": order_match.group(0)} if order_match else {}
        result = await tool_registry.execute(tool_name, params, context)
        state.tool_calls.append({"name": tool_name, "params": params, "result": result})
        if result.get("success"):
            state.final_answer = _format_tool_result(tool_name, result)
        else:
            state.final_answer = str(result.get("error", "业务查询暂时失败，请稍后重试。"))
        return state

    # 4. Retrieve evidence and enforce the pre-generation confidence gate.
    if rag_engine:
        results = rag_engine.retrieve(query, top_k=3)
        state.retrieved_chunks = [
            {
                "chunk_id": result.chunk.chunk_id,
                "title": result.chunk.title_path,
                "content": result.chunk.content,
                "score": result.score,
            }
            for result in results
        ]
        gate = confidence_gate or ConfidenceGate()
        decision = gate.evaluate(query, results)
        state.confidence_score = decision.confidence_score
        if not decision.passed:
            state.final_answer = decision.rejection_answer or "当前没有足够证据回答该问题。"
            if problem_pool_service:
                await problem_pool_service.add_or_merge_problem(
                    session_id=state.session_id,
                    trigger_type=TriggerType.CONFIDENCE_GATE,
                    query=state.query,
                    rewritten_query=query,
                    retrieved_chunks=state.retrieved_chunks,
                    answer=state.final_answer,
                )
            state.thoughts.append("证据不足，置信度闸门已拒绝生成并记录待审核问题。")
            return state

        best_chunk = results[0].chunk
        state.final_answer = f"{best_chunk.content}\n\n【依据政策来源】：《{best_chunk.title_path}》"
        state.thoughts.append(
            f"检索成功命中证据（相关度 {results[0].score:.2f}），附带政策引用生成回答。"
        )
        return state

    state.final_answer = "当前知识库服务不可用，请稍后重试或联系人工客服。"
    return state


def _format_tool_result(tool_name: str, result: dict) -> str:
    """Render structured business-tool output without exposing internal details."""
    if tool_name == "query_order":
        order = result["order"]
        return (
            f"订单 {order['order_id']}：{order['product_name']}，金额 ¥{order['amount']:.2f}，"
            f"当前状态 {order['status']}。"
        )
    if tool_name == "query_logistics":
        logistics = result["logistics"]
        return (
            f"订单 {logistics['order_id']} 由 {logistics['carrier']} 承运，"
            f"运单号 {logistics['tracking_number']}，当前状态 {logistics['status']}。"
        )
    orders = result.get("orders", [])
    if not orders:
        return "当前账户下没有可查询的订单。"
    return "\n".join(
        f"{order['order_id']}：{order['product_name']}，状态 {order['status']}"
        for order in orders
    )
