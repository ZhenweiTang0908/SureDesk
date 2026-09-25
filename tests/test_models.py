"""Unit tests for domain models, database persistence, and IDOR isolation."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from newcode.models.base import Base
from newcode.models.domain import (
    AuditLog,
    AuditStatus,
    ChatMessage,
    ChatSession,
    Logistics,
    OperatorStatus,
    Order,
    ProblemPool,
    TriggerType,
    User,
    UserRole,
)
from scripts.seed_data import seed_data


@pytest_asyncio.fixture
async def test_engine() -> AsyncEngine:
    """Provide an isolated in-memory SQLite database engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncSession:
    """Yield an active AsyncSession connected to the test database."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """Populate mock seed data into the database before test execution."""
    await seed_data(db_session)
    return db_session


@pytest.mark.asyncio
async def test_seed_data_counts_and_attributes(seeded_session: AsyncSession):
    """Verify seed data accurately creates users, orders, and logistics records."""
    # 1. Verify Users
    users_res = await seeded_session.execute(select(User).order_by(User.id))
    users = users_res.scalars().all()
    assert len(users) == 3
    user_map = {u.id: u for u in users}
    assert "user_buyer_1" in user_map
    assert user_map["user_buyer_1"].username == "买家小明"
    assert user_map["user_buyer_1"].role == UserRole.BUYER.value
    assert user_map["user_operator_1"].role == UserRole.OPERATOR.value

    # 2. Verify Orders
    orders_res = await seeded_session.execute(select(Order))
    orders = orders_res.scalars().all()
    assert len(orders) == 5

    # 3. Verify Logistics
    logistics_res = await seeded_session.execute(select(Logistics))
    logistics_list = logistics_res.scalars().all()
    assert len(logistics_list) == 3
    sf_log = next(log for log in logistics_list if log.carrier == "顺丰速运")
    assert sf_log.order_id == "order_1002"
    assert sf_log.user_id == "user_buyer_1"
    assert len(sf_log.traces) == 3


@pytest.mark.asyncio
async def test_idor_protection_order_query(seeded_session: AsyncSession):
    """Verify strict user_id scoping prevents IDOR (Insecure Direct Object Reference)."""
    buyer_1_id = "user_buyer_1"
    buyer_2_id = "user_buyer_2"
    buyer_2_order_id = "order_2001"

    # Legitimate query by owner
    stmt_owner = select(Order).where(
        Order.id == buyer_2_order_id,
        Order.user_id == buyer_2_id,
    )
    order_owner = (await seeded_session.execute(stmt_owner)).scalar_one_or_none()
    assert order_owner is not None
    assert order_owner.product_name == "客制化机械键盘 (青轴)"

    # IDOR attempt: buyer_1 attempts to access buyer_2's order
    stmt_idor = select(Order).where(
        Order.id == buyer_2_order_id,
        Order.user_id == buyer_1_id,
    )
    order_idor = (await seeded_session.execute(stmt_idor)).scalar_one_or_none()
    assert order_idor is None, "Cross-user order access must return None"

    # Record IDOR attempt into AuditLog
    audit_entry = AuditLog(
        user_id=buyer_1_id,
        action="ORDER_QUERY",
        resource_type="ORDER",
        resource_id=buyer_2_order_id,
        status=AuditStatus.BLOCKED.value,
        details={"reason": "IDOR violation: user does not own order"},
    )
    seeded_session.add(audit_entry)
    await seeded_session.commit()

    # Verify audit log was persisted
    audit_check = await seeded_session.execute(
        select(AuditLog).where(
            AuditLog.user_id == buyer_1_id,
            AuditLog.status == AuditStatus.BLOCKED.value,
        )
    )
    log_record = audit_check.scalar_one_or_none()
    assert log_record is not None
    assert log_record.resource_id == buyer_2_order_id
    assert log_record.details["reason"] == "IDOR violation: user does not own order"


@pytest.mark.asyncio
async def test_idor_protection_logistics_query(seeded_session: AsyncSession):
    """Verify user_id check prevents cross-user logistics tracking access."""
    buyer_1_id = "user_buyer_1"
    buyer_2_id = "user_buyer_2"
    target_order_id = "order_1002"  # Owned by buyer_1

    # Authorized query
    stmt_authorized = select(Logistics).where(
        Logistics.order_id == target_order_id,
        Logistics.user_id == buyer_1_id,
    )
    log_authorized = (await seeded_session.execute(stmt_authorized)).scalar_one_or_none()
    assert log_authorized is not None
    assert log_authorized.tracking_number == "SF100288889999"

    # Unauthorized query (buyer_2 tries to view buyer_1's logistics)
    stmt_unauthorized = select(Logistics).where(
        Logistics.order_id == target_order_id,
        Logistics.user_id == buyer_2_id,
    )
    log_unauthorized = (await seeded_session.execute(stmt_unauthorized)).scalar_one_or_none()
    assert log_unauthorized is None, "Cross-user logistics access must be prevented"


@pytest.mark.asyncio
async def test_chat_session_and_messages_lifecycle(db_session: AsyncSession):
    """Verify ChatSession and ChatMessage cascade, ordering, thoughts, and token tracking."""
    # 1. Create a user
    user = User(id="test_user_chat", username="测试用户", role=UserRole.BUYER.value)
    db_session.add(user)
    await db_session.flush()

    # 2. Create a session
    session = ChatSession(
        id="session_test_001",
        user_id=user.id,
        title="咨询退换货流程",
    )
    db_session.add(session)
    await db_session.flush()

    # 3. Add user and assistant messages
    msg_user = ChatMessage(
        id="msg_001",
        session_id=session.id,
        role="user",
        content="我买的椅子能退货吗？",
        tokens=15,
    )
    msg_assistant = ChatMessage(
        id="msg_002",
        session_id=session.id,
        role="assistant",
        content="支持7天无理由退货，请提供您的订单编号。",
        thoughts="识别到退货意图，查询退货政策规则库，提示用户补充订单号。",
        tokens=42,
    )
    db_session.add_all([msg_user, msg_assistant])
    await db_session.commit()

    # 4. Query session with eager-loaded messages
    query_stmt = (
        select(ChatSession)
        .where(ChatSession.id == "session_test_001")
        .options(selectinload(ChatSession.messages))
    )
    loaded_session = (await db_session.execute(query_stmt)).scalar_one()
    assert len(loaded_session.messages) == 2
    assert loaded_session.messages[0].role == "user"
    assert loaded_session.messages[1].thoughts is not None
    assert "退货政策" in loaded_session.messages[1].thoughts
    assert loaded_session.messages[1].tokens == 42

    # 5. Verify cascade deletion
    await db_session.delete(loaded_session)
    await db_session.commit()

    orphan_messages = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == "session_test_001")
        )
    ).scalars().all()
    assert len(orphan_messages) == 0, "Messages must be deleted when session is deleted"


@pytest.mark.asyncio
async def test_problem_pool_workflow(db_session: AsyncSession):
    """Verify ProblemPool captures low-confidence items and handles operator updates."""
    pool_entry = ProblemPool(
        id="prob_test_001",
        session_id="session_001",
        trigger_type=TriggerType.CONFIDENCE_GATE.value,
        query="你们支持送货上外星球吗？",
        rewritten_query="配送范围是否包括地外天体/外星球",
        retrieved_chunks=[{"chunk_id": "rule_01", "score": 0.12, "content": "国内配送政策"}],
        answer="抱歉，目前暂不支持外星球配送。",
        operator_status=OperatorStatus.PENDING.value,
    )
    db_session.add(pool_entry)
    await db_session.commit()

    # Retrieve and verify initial pending state
    entry = (
        await db_session.execute(
            select(ProblemPool).where(ProblemPool.id == "prob_test_001")
        )
    ).scalar_one()
    assert entry.operator_status == OperatorStatus.PENDING.value
    assert entry.retrieved_chunks[0]["chunk_id"] == "rule_01"

    # Operator reviews and accepts with standard answer
    entry.operator_status = OperatorStatus.ACCEPTED.value
    entry.standard_answer = "很抱歉，本店配送范围仅限中国大陆地区（部分偏远地区除外）。"
    await db_session.commit()

    # Verify update
    updated_entry = (
        await db_session.execute(
            select(ProblemPool).where(ProblemPool.id == "prob_test_001")
        )
    ).scalar_one()
    assert updated_entry.operator_status == OperatorStatus.ACCEPTED.value
    assert updated_entry.standard_answer is not None
    assert "中国大陆地区" in updated_entry.standard_answer


@pytest.mark.asyncio
async def test_audit_log_workflow(db_session: AsyncSession):
    """Verify AuditLog persists allowed and blocked events with JSON payload."""
    log_1 = AuditLog(
        user_id="user_buyer_1",
        action="REFUND_APPLY",
        resource_type="ORDER",
        resource_id="order_1001",
        status=AuditStatus.ALLOWED.value,
        details={"amount": 299.00, "status_before": "PAID_UNSHIPPED"},
    )
    db_session.add(log_1)
    await db_session.commit()

    logs = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.user_id == "user_buyer_1")
        )
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].action == "REFUND_APPLY"
    assert logs[0].status == AuditStatus.ALLOWED.value
    assert logs[0].details["amount"] == 299.00
