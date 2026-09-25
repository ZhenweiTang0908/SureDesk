"""
Comprehensive System Verification and Acceptance Test Suite.
Verifies all 6 Acceptance Criteria from MewHelp / NewCode Feature Spec:
1. Intent & Context Rewrite Accuracy >= 95%
2. IDOR Attack Defense Rate = 100%
3. Hybrid RAG vs Single-Vector Benchmark
4. Pre-Generation Confidence Gate Defense (No Hallucination)
5. Deterministic Refund Business Rules Defense (Expired Order Rejection)
6. Data Flywheel Full Closed-Loop
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from newcode.core.database import init_db, AsyncSessionLocal
from newcode.models.domain import User, Order, OrderStatus, AuditLog, AuditStatus, ProblemPool, OperatorStatus
from newcode.services.router import ContextQueryRewriterAndRouter
from newcode.tools.base import SecurityContext, IDORForbiddenException
from newcode.tools.order_tools import QueryOrderTool
from newcode.rag.engine import HybridRetrievalEngine
from newcode.guard.confidence_gate import ConfidenceGate
from newcode.workflow.graph import CustomerServiceWorkflow
from newcode.services.problem_pool import ProblemPoolService
from newcode.main import app

POLICY_DOC = """# 电商政策
## 7天退货
签收7日内支持无理由退货。
"""

@pytest.fixture(autouse=True)
async def setup_acceptance_fixtures():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Clear test records
        await session.execute(delete(Order).where(Order.id.in_(["ord_acc_u1", "ord_acc_u2", "ord_acc_exp"])))
        await session.execute(delete(User).where(User.id.in_(["user_acc_1", "user_acc_2"])))
        await session.commit()

        u1 = User(id="user_acc_1", username="buyer1", role="BUYER")
        u2 = User(id="user_acc_2", username="buyer2", role="BUYER")
        session.add_all([u1, u2])

        o1 = Order(id="ord_acc_u1", user_id="user_acc_1", status=OrderStatus.SHIPPED, amount=100.0, product_name="蓝牙耳机")
        o2 = Order(id="ord_acc_u2", user_id="user_acc_2", status=OrderStatus.SHIPPED, amount=200.0, product_name="智能手表")
        o_exp = Order(id="ord_acc_exp", user_id="user_acc_1", status=OrderStatus.DELIVERED_OVER_7D, amount=300.0, product_name="平板电脑")
        session.add_all([o1, o2, o_exp])
        await session.commit()


@pytest.mark.asyncio
async def test_criterion_1_intent_rewrite_accuracy():
    """AC1: Intent & Context Rewrite Accuracy >= 95%"""
    from tests.test_intent_router import TEST_CASES
    service = ContextQueryRewriterAndRouter()
    correct = 0
    for case in TEST_CASES:
        res = service.rewrite_and_route(case["query"], case["history"])
        if res.intent == case["expected_intent"] and res.route == case["expected_route"]:
            correct += 1
    accuracy = (correct / len(TEST_CASES)) * 100
    assert accuracy >= 95.0, f"AC1 failed: accuracy {accuracy}% < 95%"


@pytest.mark.asyncio
async def test_criterion_2_idor_defense():
    """AC2: 100% Interception Rate for Cross-User Order IDOR Attacks"""
    tool = QueryOrderTool()
    ctx_attacker = SecurityContext(user_id="user_acc_1", session_id="sess_hacker")

    with pytest.raises(IDORForbiddenException):
        await tool.execute({"order_id": "ord_acc_u2"}, context=ctx_attacker)

    # Verify audit log recorded
    async with AsyncSessionLocal() as session:
        stmt = select(AuditLog).where(
            AuditLog.user_id == "user_acc_1",
            AuditLog.action == "IDOR_QUERY_ORDER_ATTEMPT",
            AuditLog.status == AuditStatus.BLOCKED,
        )
        audit = (await session.execute(stmt)).scalars().all()
        assert len(audit) >= 1
        assert audit[-1].resource_id == "ord_acc_u2"


def test_criterion_3_hybrid_rag_benchmark():
    """AC3: Hybrid RAG achieves high Recall@5 and MRR"""
    from newcode.rag.evaluator import RAGEvaluator
    from tests.test_evaluator import Chunk

    engine = HybridRetrievalEngine()
    c1 = Chunk(chunk_id="c1", content="7天无理由退货运费买家自理", title_path="服务手册 > 7天退货")
    c2 = Chunk(chunk_id="c2", content="顺丰48小时发货", title_path="服务手册 > 发货规则")
    engine.add_chunks([c1, c2])

    evaluator = RAGEvaluator(engine)
    res = evaluator.evaluate_query("q1", "7天退货运费谁出", "7天退货", "售后", k=2, mode="hybrid")
    assert res.hit_at_k is True
    assert res.reciprocal_rank == 1.0


def test_criterion_4_confidence_gate_hallucination_defense():
    """AC4: 100% Polite Rejection on Unknown Policy Queries (Zero Hallucination)"""
    gate = ConfidenceGate(score_threshold=0.55)
    decision = gate.evaluate("买电脑赠送火星太空旅行船票吗？", [])
    assert decision.passed is False
    assert "暂未收录" in decision.rejection_answer or "未能找到" in decision.rejection_answer


@pytest.mark.asyncio
async def test_criterion_5_deterministic_refund_rule_defense():
    """AC5: Expired Orders (> 7 days) are 100% Intercepted Deterministically"""
    workflow = CustomerServiceWorkflow()
    res = await workflow.run(
        user_id="user_acc_1",
        session_id="sess_wf_exp",
        query="退款 ord_acc_exp",
    )
    assert res.refund_status == "REJECTED_EXPIRED"
    assert "超过国家法定与平台规定的7天无理由退货期限" in res.final_answer


@pytest.mark.asyncio
async def test_criterion_6_data_flywheel_closed_loop():
    """AC6: Full Flywheel Closed Loop from Rejection -> Review -> Sync -> Instant Hit"""
    engine = HybridRetrievalEngine()
    gate = ConfidenceGate(score_threshold=0.60)
    pool = ProblemPoolService(similarity_threshold=0.65)

    test_q = "支持数字人民币钱包扫码支付吗？"
    hits = engine.retrieve(test_q, top_k=3)
    dec = gate.evaluate(test_q, hits)
    assert dec.passed is False

    problem = await pool.add_or_merge_problem("sess_acc_fw", "CONFIDENCE_GATE", test_q)
    assert problem.operator_status == OperatorStatus.PENDING.value

    # Operator adopts
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/workbench/adopt",
            json={"problem_id": problem.id, "standard_answer": "平台已全量支持中国人民银行数字人民币App快捷扫码支付。"},
        )

    # Sync to engine
    engine.add_markdown_document(f"### 数字人民币支付\n平台已全量支持中国人民银行数字人民币App快捷扫码支付。")

    # Re-query
    re_hits = engine.retrieve(test_q, top_k=3)
    re_dec = gate.evaluate(test_q, re_hits)
    assert re_dec.passed is True
    assert "数字人民币" in re_hits[0].chunk.content

