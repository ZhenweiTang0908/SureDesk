"""
State definitions for LangGraph customer service workflow.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from newcode.schemas.intent import IntentType, RouteTarget


class CustomerServiceState(BaseModel):
    session_id: str
    user_id: str
    query: str
    rewritten_query: str = ""
    intent: IntentType | None = None
    route: RouteTarget | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)

    # Workflow slots
    order_id: str | None = None
    refund_status: Literal["NONE", "PENDING_ORDER_ID", "APPROVED", "REJECTED_EXPIRED", "REJECTED_POLICY"] = "NONE"
    refund_voucher: str | None = None
    is_suspended: bool = False
    pending_prompt: str | None = None

    # Agent execution details
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = 1.0
    final_answer: str = ""
    thoughts: list[str] = Field(default_factory=list)

