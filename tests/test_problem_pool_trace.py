"""
Unit tests for ProblemPoolService (3 entrance triggers, deduplication) and RequestTracer.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from newcode.core.database import init_db, AsyncSessionLocal
from newcode.models.domain import ProblemPool, TriggerType, OperatorStatus, AuditLog, AuditStatus
from newcode.services.problem_pool import ProblemPoolService, compute_text_similarity
from newcode.core.tracing import RequestTracer
from newcode.main import app


@pytest.fixture(autouse=True)
async def clean_problem_pool():
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProblemPool))
        await session.execute(delete(AuditLog).where(AuditLog.action == "REQUEST_TRACE"))
        await session.commit()


def test_compute_text_similarity():
    sim1 = compute_text_similarity("生鲜食品能退货吗？", "生鲜食品支持退货吗")
    assert sim1 >= 0.70

    sim2 = compute_text_similarity("顺丰包邮吗", "发票怎么开")
    assert sim2 < 0.20


@pytest.mark.asyncio
async def test_problem_pool_three_triggers_and_deduplication():
    service = ProblemPoolService(similarity_threshold=0.70)

    # 1. Trigger 1: CONFIDENCE_GATE
    p1 = await service.add_or_merge_problem(
        session_id="sess_1",
        trigger_type=TriggerType.CONFIDENCE_GATE,
        query="火星地址包邮吗？",
        rewritten_query="火星地址是否支持包邮？",
        retrieved_chunks=[],
        answer="暂未收录该政策",
    )
    assert p1.id is not None
    assert p1.frequency == 1
    assert p1.trigger_type == TriggerType.CONFIDENCE_GATE

    # 2. Duplicate / near-duplicate query -> merges and increments frequency
    p1_dup = await service.add_or_merge_problem(
        session_id="sess_2",
        trigger_type=TriggerType.CONFIDENCE_GATE,
        query="火星地址包邮么",
        rewritten_query="火星地址是否支持包邮么？",
    )
    assert p1_dup.id == p1.id
    assert p1_dup.frequency == 2
    assert "sess_2" in p1_dup.sessions

    # 3. Trigger 2: SELF_EVAL_FAIL
    p2 = await service.add_or_merge_problem(
        session_id="sess_3",
        trigger_type=TriggerType.SELF_EVAL_FAIL,
        query="买三件能送一台无人机吗？",
    )
    assert p2.id != p1.id
    assert p2.trigger_type == TriggerType.SELF_EVAL_FAIL


@pytest.mark.asyncio
async def test_feedback_api_thumbs_down_ingestion():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Negative feedback
        resp = await client.post(
            "/api/feedback",
            json={
                "user_id": "user_buyer_1",
                "session_id": "sess_feedback",
                "query": "你们家的耳机防水等级是多少？",
                "answer": "我不知道",
                "useful": False,
                "comment": "回答太敷衍，未给出IPX等级",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["frequency"] == 1

        # Check DB
        async with AsyncSessionLocal() as session:
            stmt = select(ProblemPool).where(ProblemPool.trigger_type == TriggerType.USER_THUMBS_DOWN)
            item = (await session.execute(stmt)).scalar_one_or_none()
            assert item is not None
            assert "耳机防水等级" in item.query


@pytest.mark.asyncio
async def test_request_tracer_and_audit_persistence():
    tracer = RequestTracer(user_id="user_trace_test", session_id="sess_trace")
    s1 = tracer.start_span("intent_rewrite")
    s1.finish(route="MAIN_AGENT_RAG")

    s2 = tracer.start_span("hybrid_retrieval")
    s2.finish(top_k=3)

    tracer.set_tokens(prompt=120, completion=45)
    tracer.record_evidence([{"chunk_id": "c1", "title": "7天无理由退货"}])

    trace_data = tracer.to_dict()
    assert trace_data["total_tokens"] == 165
    assert trace_data["evidence_count"] == 1
    assert len(trace_data["spans"]) == 2

    # Persist to AuditLog
    await tracer.persist_audit()

    async with AsyncSessionLocal() as session:
        stmt = select(AuditLog).where(
            AuditLog.user_id == "user_trace_test",
            AuditLog.action == "REQUEST_TRACE",
        )
        log = (await session.execute(stmt)).scalar_one_or_none()
        assert log is not None
        assert log.status == AuditStatus.ALLOWED
        assert log.details["total_tokens"] == 165

