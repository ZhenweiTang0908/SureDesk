"""
Schemas for 9 Intent Types and 5 Route Destinations.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    PRODUCT_CONSULTATION = "PRODUCT_CONSULTATION"    # 1. Product consultation (specs, params, features)
    PRE_SALE_RULES = "PRE_SALE_RULES"                # 2. Pre-sale rules (price match, coupon, invoice, etc.)
    ORDER_QUERY = "ORDER_QUERY"                      # 3. Order status & history query
    LOGISTICS_PROGRESS = "LOGISTICS_PROGRESS"        # 4. Logistics shipment & tracking
    REFUND_REQUEST = "REFUND_REQUEST"                # 5. Refund or return request
    COMPLAINT_HUMAN = "COMPLAINT_HUMAN"              # 6. Complaint or transfer to human agent
    CHITCHAT = "CHITCHAT"                            # 7. Casual chitchat & greetings
    SENSITIVE_VIOLATION = "SENSITIVE_VIOLATION"      # 8. Sensitive or policy violation
    PENDING_CLARIFICATION = "PENDING_CLARIFICATION"  # 9. Incomplete query / missing required slots


class RouteTarget(str, Enum):
    FALLBACK_DIRECT = "FALLBACK_DIRECT"              # 1. Direct fallback response (chitchat / violation)
    TRANSFER_HUMAN = "TRANSFER_HUMAN"                # 2. Transfer to human / create support ticket
    CLARIFY_PROMPT = "CLARIFY_PROMPT"                # 3. Request slot clarification from buyer
    DETERMINISTIC_WORKFLOW = "DETERMINISTIC_WORKFLOW"# 4. Deterministic workflow (refund state machine)
    MAIN_AGENT_RAG = "MAIN_AGENT_RAG"                # 5. Main Agent / RAG knowledge base QA


class RewriteAndRouteResult(BaseModel):
    original_query: str = Field(..., description="Original raw user query")
    rewritten_query: str = Field(..., description="Semantically complete query after pronoun resolution")
    intent: IntentType = Field(..., description="One of the 9 fine-grained intent types")
    route: RouteTarget = Field(..., description="One of the 5 routing destinations")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    missing_slots: list[str] = Field(default_factory=list, description="Missing essential entity slots")
    reasoning: str = Field(default="", description="Reasoning explanation for classification and routing")

