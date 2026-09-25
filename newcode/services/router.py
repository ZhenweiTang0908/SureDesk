"""
Context-Aware Query Rewriter and 9-Intent 5-Route Classifier.
"""
from __future__ import annotations

import re
from typing import Any
from newcode.schemas.intent import IntentType, RouteTarget, RewriteAndRouteResult


# Rule-based intent keyword mapping
INTENT_KEYWORDS: dict[IntentType, list[str]] = {
    IntentType.SENSITIVE_VIOLATION: ["色情", "暴力", "炸弹", "违法", "赌博", "枪支", "毒品", "政治敏感"],
    IntentType.COMPLAINT_HUMAN: ["人工", "转人工", "投诉", "我要找人", "叫客服经理", "差评曝光", "态度太差", "315", "消协"],
    IntentType.REFUND_REQUEST: ["退款", "退货", "换货", "退钱", "不要了", "申请退款", "退回商品"],
    IntentType.LOGISTICS_PROGRESS: ["物流", "快递", "发货了吗", "查件", "运单号", "到哪了", "顺丰", "催单", "还没发货", "发货", "配送"],
    IntentType.ORDER_QUERY: ["查订单", "我的订单", "订单状态", "订单号", "买了什么", "买过什么", "查看购买记录", "订单记录"],
    IntentType.PRE_SALE_RULES: ["保价", "价格保护", "优惠券", "发票", "支持7天", "七天无理由", "包邮", "满减", "专享券", "保修", "质保"],
    IntentType.PRODUCT_CONSULTATION: ["参数", "配置", "尺寸", "颜色", "功能", "规格", "好用吗", "材质", "重量", "续航"],
    IntentType.CHITCHAT: ["你好", "在吗", "早上好", "晚上好", "谢谢", "再见", "你是谁", "讲个笑话", "哈哈"],
}


def map_intent_to_route(intent: IntentType, missing_slots: list[str]) -> RouteTarget:
    """Deterministic mapping from 9 intents to 5 route targets."""
    if missing_slots:
        return RouteTarget.CLARIFY_PROMPT

    if intent in (IntentType.CHITCHAT, IntentType.SENSITIVE_VIOLATION):
        return RouteTarget.FALLBACK_DIRECT
    elif intent == IntentType.COMPLAINT_HUMAN:
        return RouteTarget.TRANSFER_HUMAN
    elif intent == IntentType.PENDING_CLARIFICATION:
        return RouteTarget.CLARIFY_PROMPT
    elif intent == IntentType.REFUND_REQUEST:
        return RouteTarget.DETERMINISTIC_WORKFLOW
    else:  # PRODUCT_CONSULTATION, PRE_SALE_RULES, ORDER_QUERY, LOGISTICS_PROGRESS
        return RouteTarget.MAIN_AGENT_RAG


class ContextQueryRewriterAndRouter:
    """
    Combines context resolution, pronoun restoration, intent classification, and route mapping.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def rewrite_and_route(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
    ) -> RewriteAndRouteResult:
        query_strip = query.strip()
        history = history or []

        # 1. Check for sensitive violation first
        for kw in INTENT_KEYWORDS[IntentType.SENSITIVE_VIOLATION]:
            if kw in query_strip:
                return RewriteAndRouteResult(
                    original_query=query_strip,
                    rewritten_query=query_strip,
                    intent=IntentType.SENSITIVE_VIOLATION,
                    route=RouteTarget.FALLBACK_DIRECT,
                    confidence=1.0,
                    reasoning="命中敏感违规词汇",
                )

        # 2. Context resolution and pronoun disambiguation
        rewritten = query_strip
        last_subject = ""

        # Extract last mentioned product or entity from history
        for msg in reversed(history):
            content = msg.get("content", "")
            match = re.search(r"([A-Za-z0-9\u4e00-\u9fff]{2,15}(?:耳机|手机|电脑|相机|手表|鞋|衣服|包|商品|订单[A-Za-z0-9_]*))", content)
            if match:
                last_subject = match.group(1)
                break

        # Disambiguate pronouns: 它, 这个, 那件, 该商品, etc.
        pronouns = ["它", "这个", "那件", "该商品", "这款", "那", "它的"]
        for p in pronouns:
            if p in query_strip and last_subject:
                rewritten = re.sub(rf"^{p}", last_subject, query_strip)
                if rewritten == query_strip:
                    rewritten = query_strip.replace(p, last_subject)
                break

        # If query is short half-sentence
        if len(query_strip) <= 6 and last_subject and last_subject not in query_strip:
            if "退" in query_strip:
                rewritten = f"{last_subject}支持退款退货吗？"
            elif "保修" in query_strip:
                rewritten = f"{last_subject}保修多久？"
            elif "发货" in query_strip:
                rewritten = f"{last_subject}什么时候发货？"

        # 3. Intent Classification
        detected_intent = None

        # Check complaint
        for kw in INTENT_KEYWORDS[IntentType.COMPLAINT_HUMAN]:
            if kw in query_strip:
                detected_intent = IntentType.COMPLAINT_HUMAN
                break

        # Check refund
        if detected_intent is None:
            for kw in INTENT_KEYWORDS[IntentType.REFUND_REQUEST]:
                if kw in query_strip or kw in rewritten:
                    detected_intent = IntentType.REFUND_REQUEST
                    break

        # Check pre-sale rules
        if detected_intent is None:
            for kw in INTENT_KEYWORDS[IntentType.PRE_SALE_RULES]:
                if kw in query_strip or kw in rewritten:
                    detected_intent = IntentType.PRE_SALE_RULES
                    break

        # Check logistics
        if detected_intent is None:
            for kw in INTENT_KEYWORDS[IntentType.LOGISTICS_PROGRESS]:
                if kw in query_strip or kw in rewritten:
                    detected_intent = IntentType.LOGISTICS_PROGRESS
                    break

        # Check order query
        if detected_intent is None:
            for kw in INTENT_KEYWORDS[IntentType.ORDER_QUERY]:
                if kw in query_strip or kw in rewritten:
                    detected_intent = IntentType.ORDER_QUERY
                    break

        # Check chitchat
        if detected_intent is None:
            for kw in INTENT_KEYWORDS[IntentType.CHITCHAT]:
                if query_strip == kw or query_strip.startswith(kw):
                    detected_intent = IntentType.CHITCHAT
                    break

        # Check product consultation
        if detected_intent is None:
            for kw in INTENT_KEYWORDS[IntentType.PRODUCT_CONSULTATION]:
                if kw in query_strip or kw in rewritten:
                    detected_intent = IntentType.PRODUCT_CONSULTATION
                    break

        if detected_intent is None:
            detected_intent = IntentType.PRODUCT_CONSULTATION

        # Ambiguous check
        missing_slots = []
        if query_strip in ["能退吗", "好不好", "多少钱", "什么时候"] and not last_subject:
            detected_intent = IntentType.PENDING_CLARIFICATION
            missing_slots = ["subject_entity"]

        route = map_intent_to_route(detected_intent, missing_slots)

        return RewriteAndRouteResult(
            original_query=query_strip,
            rewritten_query=rewritten,
            intent=detected_intent,
            route=route,
            confidence=0.98,
            missing_slots=missing_slots,
            reasoning=f"意图识别为 {detected_intent.value}，路由出口分流至 {route.value}",
        )

