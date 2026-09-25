"""
Unit tests for Query Rewriting, Pronoun Resolution, 9 Intents and 5 Routes.
"""
import pytest
from newcode.schemas.intent import IntentType, RouteTarget
from newcode.services.router import ContextQueryRewriterAndRouter

TEST_CASES = [
    # 1. Pronoun resolution: "它" with prior context
    {
        "query": "那它能退吗？",
        "history": [{"role": "user", "content": "我想了解无线降噪耳机"}],
        "expected_intent": IntentType.REFUND_REQUEST,
        "expected_route": RouteTarget.DETERMINISTIC_WORKFLOW,
        "contains_in_rewritten": "无线降噪耳机",
    },
    # 2. Pronoun resolution: "这个"
    {
        "query": "这个保修多久？",
        "history": [{"role": "user", "content": "看中了那款智能旗舰手机"}],
        "expected_intent": IntentType.PRE_SALE_RULES,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "智能旗舰手机",
    },
    # 3. Half-sentence: "什么时候发货？"
    {
        "query": "什么时候发货？",
        "history": [{"role": "user", "content": "我的订单ord_1001还没动静"}],
        "expected_intent": IntentType.LOGISTICS_PROGRESS,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "发货",
    },
    # 4. Sensitive violation
    {
        "query": "你们卖枪支弹药违禁品吗？",
        "history": [],
        "expected_intent": IntentType.SENSITIVE_VIOLATION,
        "expected_route": RouteTarget.FALLBACK_DIRECT,
        "contains_in_rewritten": "枪支",
    },
    # 5. Chitchat: 你好
    {
        "query": "你好",
        "history": [],
        "expected_intent": IntentType.CHITCHAT,
        "expected_route": RouteTarget.FALLBACK_DIRECT,
        "contains_in_rewritten": "你好",
    },
    # 6. Complaint / Transfer to Human
    {
        "query": "我要找人工客服，你们态度太差了！",
        "history": [],
        "expected_intent": IntentType.COMPLAINT_HUMAN,
        "expected_route": RouteTarget.TRANSFER_HUMAN,
        "contains_in_rewritten": "人工",
    },
    # 7. Complaint: 投诉
    {
        "query": "我要投诉你们，向315举报！",
        "history": [],
        "expected_intent": IntentType.COMPLAINT_HUMAN,
        "expected_route": RouteTarget.TRANSFER_HUMAN,
        "contains_in_rewritten": "投诉",
    },
    # 8. Refund request directly
    {
        "query": "申请退款订单 ord_2001",
        "history": [],
        "expected_intent": IntentType.REFUND_REQUEST,
        "expected_route": RouteTarget.DETERMINISTIC_WORKFLOW,
        "contains_in_rewritten": "ord_2001",
    },
    # 9. Order query
    {
        "query": "帮我查一下我的订单记录",
        "history": [],
        "expected_intent": IntentType.ORDER_QUERY,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "订单",
    },
    # 10. Logistics progress
    {
        "query": "物流单号SF10001到哪了？",
        "history": [],
        "expected_intent": IntentType.LOGISTICS_PROGRESS,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "SF10001",
    },
    # 11. Pre-sale rule: 价格保护
    {
        "query": "你们支持7天保价退差价吗？",
        "history": [],
        "expected_intent": IntentType.PRE_SALE_RULES,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "保价",
    },
    # 12. Pre-sale rule: 发票
    {
        "query": "能开增值税专用发票吗？",
        "history": [],
        "expected_intent": IntentType.PRE_SALE_RULES,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "发票",
    },
    # 13. Pre-sale rule: 优惠券
    {
        "query": "优惠券怎么使用，可以叠加吗？",
        "history": [],
        "expected_intent": IntentType.PRE_SALE_RULES,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "优惠券",
    },
    # 14. Product consultation
    {
        "query": "这款耳机的电池续航参数是多少小时？",
        "history": [],
        "expected_intent": IntentType.PRODUCT_CONSULTATION,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "参数",
    },
    # 15. Product consultation with context
    {
        "query": "它的重量是多少克？",
        "history": [{"role": "user", "content": "这台轻薄笔记本电脑怎么样"}],
        "expected_intent": IntentType.PRODUCT_CONSULTATION,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "笔记本电脑",
    },
    # 16. Ambiguous question without context -> Pending clarification
    {
        "query": "能退吗",
        "history": [],
        "expected_intent": IntentType.PENDING_CLARIFICATION,
        "expected_route": RouteTarget.CLARIFY_PROMPT,
        "contains_in_rewritten": "能退吗",
    },
    # 17. Ambiguous price without context
    {
        "query": "多少钱",
        "history": [],
        "expected_intent": IntentType.PENDING_CLARIFICATION,
        "expected_route": RouteTarget.CLARIFY_PROMPT,
        "contains_in_rewritten": "多少钱",
    },
    # 18. Half-sentence refund with context
    {
        "query": "那我要退货",
        "history": [{"role": "user", "content": "我买了智能旗舰手机"}],
        "expected_intent": IntentType.REFUND_REQUEST,
        "expected_route": RouteTarget.DETERMINISTIC_WORKFLOW,
        "contains_in_rewritten": "智能旗舰手机",
    },
    # 19. Chitchat: 谢谢
    {
        "query": "谢谢你",
        "history": [],
        "expected_intent": IntentType.CHITCHAT,
        "expected_route": RouteTarget.FALLBACK_DIRECT,
        "contains_in_rewritten": "谢谢",
    },
    # 20. Logistics inquiry: 还没发货
    {
        "query": "为什么三天了还没发货呢？",
        "history": [],
        "expected_intent": IntentType.LOGISTICS_PROGRESS,
        "expected_route": RouteTarget.MAIN_AGENT_RAG,
        "contains_in_rewritten": "发货",
    },
]


def test_20_intent_and_routing_cases():
    service = ContextQueryRewriterAndRouter()
    correct_intents = 0
    correct_routes = 0

    for idx, case in enumerate(TEST_CASES, start=1):
        result = service.rewrite_and_route(case["query"], case["history"])

        # Validate Intent
        assert result.intent == case["expected_intent"], (
            f"Case #{idx} failed intent: expected {case['expected_intent']}, got {result.intent}"
        )
        correct_intents += 1

        # Validate Route
        assert result.route == case["expected_route"], (
            f"Case #{idx} failed route: expected {case['expected_route']}, got {result.route}"
        )
        correct_routes += 1

        # Validate pronoun / entity resolution in rewritten query
        assert case["contains_in_rewritten"] in result.rewritten_query, (
            f"Case #{idx} failed rewrite: '{case['contains_in_rewritten']}' not in '{result.rewritten_query}'"
        )

    accuracy = (correct_intents / len(TEST_CASES)) * 100
    assert accuracy >= 95.0, f"Intent accuracy {accuracy}% below 95% threshold"

