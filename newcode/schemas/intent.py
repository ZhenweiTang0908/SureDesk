"""
Schemas for 9 Intent Types and 5 Route Destinations.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    PRODUCT_CONSULTATION = "PRODUCT_CONSULTATION"    # 1. 商品咨询
    PRE_SALE_RULES = "PRE_SALE_RULES"                # 2. 售前规则（价格保护、优惠券、发票等）
    ORDER_QUERY = "ORDER_QUERY"                      # 3. 订单查询
    LOGISTICS_PROGRESS = "LOGISTICS_PROGRESS"        # 4. 物流进度
    REFUND_REQUEST = "REFUND_REQUEST"                # 5. 退款申请/退货
    COMPLAINT_HUMAN = "COMPLAINT_HUMAN"              # 6. 投诉/转人工
    CHITCHAT = "CHITCHAT"                            # 7. 闲聊
    SENSITIVE_VIOLATION = "SENSITIVE_VIOLATION"      # 8. 敏感违规
    PENDING_CLARIFICATION = "PENDING_CLARIFICATION"  # 9. 未决追问/关键信息缺失


class RouteTarget(str, Enum):
    FALLBACK_DIRECT = "FALLBACK_DIRECT"              # 1. 直接兜底回复 (闲聊/违规)
    TRANSFER_HUMAN = "TRANSFER_HUMAN"                # 2. 转人工 / 建工单
    CLARIFY_PROMPT = "CLARIFY_PROMPT"                # 3. 业务信息追问 (信息缺失)
    DETERMINISTIC_WORKFLOW = "DETERMINISTIC_WORKFLOW"# 4. 确定性 Workflow 子流程 (退款退货)
    MAIN_AGENT_RAG = "MAIN_AGENT_RAG"                # 5. 主力 Agent / RAG 知识检索问答


class RewriteAndRouteResult(BaseModel):
    original_query: str = Field(..., description="用户原始半截话或提问")
    rewritten_query: str = Field(..., description="结合上下文指代消解补全后的语义完整提问")
    intent: IntentType = Field(..., description="9 类细分意图之一")
    route: RouteTarget = Field(..., description="5 大路由执行出口之一")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度评分")
    missing_slots: list[str] = Field(default_factory=list, description="缺失的关键要素槽位")
    reasoning: str = Field(default="", description="意图识别与改写逻辑说明")

