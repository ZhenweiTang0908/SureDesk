"""
End-to-End closed-loop test for Data Flywheel:
1. Ask unknown policy query -> Gate rejects & enters Problem Pool
2. Operator workbench reviews pending problems -> Adopts standard answer
3. Vector/Knowledge engine updates
4. Re-query -> Successfully hits newly updated knowledge!
"""
import pytest
from httpx import AsyncClient, ASGITransport
from newcode.core.database import init_db, AsyncSessionLocal
from newcode.models.domain import ProblemPool, OperatorStatus, TriggerType
from newcode.rag.engine import HybridRetrievalEngine
from newcode.guard.confidence_gate import ConfidenceGate
from newcode.services.problem_pool import ProblemPoolService
from newcode.main import app


@pytest.fixture(autouse=True)
async def init_database():
    await init_db()


@pytest.mark.asyncio
async def test_end_to_end_flywheel_closed_loop():
    engine = HybridRetrievalEngine()
    gate = ConfidenceGate(score_threshold=0.60)
    pool_service = ProblemPoolService(similarity_threshold=0.65)

    test_query = "购买手机后赠送碎屏险吗？"

    # Step 1: Initial query when knowledge base is blank on this topic
    hits = engine.retrieve(test_query, top_k=3)
    decision = gate.evaluate(test_query, hits)

    assert decision.passed is False
    assert "未收录" in decision.rejection_answer or "未能找到" in decision.rejection_answer

    # Automatic ingestion into problem pool
    problem = await pool_service.add_or_merge_problem(
        session_id="sess_e2e_user",
        trigger_type=TriggerType.CONFIDENCE_GATE,
        query=test_query,
        rewritten_query=test_query,
        retrieved_chunks=[],
        answer=decision.rejection_answer,
    )
    assert problem.id is not None
    assert problem.operator_status == OperatorStatus.PENDING.value

    # Step 2: Operator lists pending problems via workbench API
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get("/api/workbench/problems?status=PENDING")
        assert list_resp.status_code == 200
        problems = list_resp.json()["problems"]
        target = next((p for p in problems if p["id"] == problem.id), None)
        assert target is not None
        assert target["query"] == test_query

        # Step 3: Operator adopts standard answer via workbench API
        std_answer = "凡在官方旗舰店购买任意型号智能手机，均免费获赠一年原厂碎屏保，碎屏支持免费换新一次。"
        adopt_resp = await client.post(
            "/api/workbench/adopt",
            json={"problem_id": problem.id, "standard_answer": std_answer},
        )
        assert adopt_resp.status_code == 200
        assert adopt_resp.json()["success"] is True

        # Step 4: Knowledge base syncs the newly adopted FAQ chunk
        adopted_doc = f"# 售后与增值保障\n\n### 手机碎屏险服务\n{std_answer}"
        engine.add_markdown_document(adopted_doc, source_doc="运营审核知识库回流")

    # Step 5: User queries the same question again
    re_hits = engine.retrieve(test_query, top_k=3)
    re_decision = gate.evaluate(test_query, re_hits)

    # Now confidence gate passes!
    assert re_decision.passed is True
    assert len(re_hits) > 0
    top_hit = re_hits[0].chunk
    assert "手机碎屏险服务" in top_hit.title_path
    assert "免费获赠一年原厂碎屏保" in top_hit.content

