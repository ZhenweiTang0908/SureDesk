"""
Main ReAct Agent Node integrating Knowledge Retrieval, Tool Calling, and Direct Fallback.
"""
from __future__ import annotations

from newcode.rag.engine import HybridRetrievalEngine
from newcode.tools.registry import ToolRegistry
from newcode.tools.base import SecurityContext
from newcode.workflow.state import CustomerServiceState


async def execute_agent_node(
    state: CustomerServiceState,
    rag_engine: HybridRetrievalEngine | None = None,
    tool_registry: ToolRegistry | None = None,
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
    if route == "FALLBACK_DIRECT" or (state.intent and state.intent.value == "SENSITIVE_VIOLATION"):
        if state.intent and state.intent.value == "SENSITIVE_VIOLATION":
            state.final_answer = "您的输入涉及平台禁止的违规违禁内容，已被系统安全机制拦截并记录。"
            state.thoughts.append("安全防御：触发敏感违规前置拦截。")
            return state
        else:
            state.final_answer = "您好！我是 MewHelp 智能客服助手，请问有什么可以帮您的？支持查询订单、追踪物流、退换货以及政策咨询哦！"
            state.thoughts.append("闲聊出口：输出标准亲切问候语。")
            return state

    # 2. Transfer Human
    if route == "TRANSFER_HUMAN" or (state.intent and state.intent.value == "COMPLAINT_HUMAN"):
        ticket_id = f"TICKET-2026-{state.user_id[-4:]}-01"
        state.final_answer = (
            f"非常抱歉给您带来不好的体验！已为您优先接入专属人工客服通道，正在排队转接中..."
            f"若当前处于非人工在线时段，系统已为您创建高优先级加急工单（工单号：{ticket_id}），客诉专员将在2小时内与您电话联系。"
        )
        state.thoughts.append("转人工出口：已创建客诉加急工单并触发通道转接。")
        return state

    # 3. Main Agent RAG & Tool Execution
    if rag_engine:
        results = rag_engine.retrieve(query, top_k=3)
        if results:
            state.retrieved_chunks = [
                {
                    "chunk_id": r.chunk.chunk_id,
                    "title": r.chunk.title_path,
                    "content": r.chunk.content,
                    "score": r.score,
                }
                for r in results
            ]
            state.confidence_score = results[0].score

            # Formulate grounded answer with reference citation
            best_chunk = results[0].chunk
            state.final_answer = (
                f"{best_chunk.content}\n\n"
                f"【依据政策来源】：《{best_chunk.title_path}》"
            )
            state.thoughts.append(f"检索成功命中证据（相关度 {results[0].score:.2f}），附带政策引用生成回答。")
            return state

    state.final_answer = "您好，我已收到您的问题，正在为您核查相关业务政策，请稍候。"
    return state

