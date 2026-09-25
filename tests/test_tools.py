"""
Unit tests for Business Tools, IDOR Protection, Tool Registry, and MCP Adapter.
"""
import pytest
from sqlalchemy import select, delete
from newcode.core.database import init_db, AsyncSessionLocal
from newcode.models.domain import User, Order, Logistics, OrderStatus, LogisticsStatus, AuditLog, AuditStatus
from newcode.tools.base import SecurityContext, IDORForbiddenException
from newcode.tools.order_tools import QueryOrderTool, ListOrdersTool
from newcode.tools.logistics_tools import QueryLogisticsTool
from newcode.tools.mcp_adapter import MCPToolAdapter
from newcode.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Clean existing test records
        await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(["user_alice", "user_bob"])))
        await session.execute(delete(Logistics).where(Logistics.id.in_(["log_alice_1", "log_bob_1"])))
        await session.execute(delete(Order).where(Order.id.in_(["ord_alice_1", "ord_bob_1"])))
        await session.execute(delete(User).where(User.id.in_(["user_alice", "user_bob"])))
        await session.commit()

        # Create test users
        u1 = User(id="user_alice", username="alice", role="BUYER")
        u2 = User(id="user_bob", username="bob", role="BUYER")
        session.add_all([u1, u2])

        # Create orders
        o1 = Order(
            id="ord_alice_1",
            user_id="user_alice",
            status=OrderStatus.SHIPPED,
            amount=299.0,
            product_name="无线降噪耳机",
        )
        o2 = Order(
            id="ord_bob_1",
            user_id="user_bob",
            status=OrderStatus.DELIVERED_OVER_7D,
            amount=4999.0,
            product_name="智能旗舰手机",
        )
        session.add_all([o1, o2])

        # Create logistics
        l1 = Logistics(
            id="log_alice_1",
            order_id="ord_alice_1",
            user_id="user_alice",
            tracking_number="SF10001",
            carrier="顺丰速运",
            status=LogisticsStatus.IN_TRANSIT,
            traces=[{"time": "2026-09-24 10:00", "event": "已揽收"}],
        )
        l2 = Logistics(
            id="log_bob_1",
            order_id="ord_bob_1",
            user_id="user_bob",
            tracking_number="SF10002",
            carrier="顺丰速运",
            status=LogisticsStatus.DELIVERED,
            traces=[{"time": "2026-09-10 12:00", "event": "已签收"}],
        )
        session.add_all([l1, l2])
        await session.commit()


@pytest.mark.asyncio
async def test_query_own_order_success():
    tool = QueryOrderTool()
    ctx = SecurityContext(user_id="user_alice")
    result = await tool.execute({"order_id": "ord_alice_1"}, context=ctx)
    assert result["success"] is True
    assert result["order"]["product_name"] == "无线降噪耳机"
    assert result["order"]["amount"] == 299.0


@pytest.mark.asyncio
async def test_query_cross_user_order_idor_blocked():
    tool = QueryOrderTool()
    ctx = SecurityContext(user_id="user_alice", session_id="sess_hacker")
    with pytest.raises(IDORForbiddenException) as exc_info:
        await tool.execute({"order_id": "ord_bob_1"}, context=ctx)

    assert "越权访问拦截" in str(exc_info.value)

    async with AsyncSessionLocal() as session:
        stmt = select(AuditLog).where(
            AuditLog.user_id == "user_alice",
            AuditLog.action == "IDOR_QUERY_ORDER_ATTEMPT",
            AuditLog.status == AuditStatus.BLOCKED,
        )
        audits = (await session.execute(stmt)).scalars().all()
        assert len(audits) >= 1
        assert audits[-1].resource_id == "ord_bob_1"


@pytest.mark.asyncio
async def test_query_logistics_and_idor_blocked():
    tool = QueryLogisticsTool()
    ctx_alice = SecurityContext(user_id="user_alice")
    res_ok = await tool.execute({"order_id": "ord_alice_1"}, context=ctx_alice)
    assert res_ok["success"] is True
    assert res_ok["logistics"]["tracking_number"] == "SF10001"

    with pytest.raises(IDORForbiddenException):
        await tool.execute({"order_id": "ord_bob_1"}, context=ctx_alice)


@pytest.mark.asyncio
async def test_list_orders_only_returns_own_orders():
    tool = ListOrdersTool()
    ctx_alice = SecurityContext(user_id="user_alice")
    res = await tool.execute({}, context=ctx_alice)
    assert res["success"] is True
    assert res["total"] == 1
    assert res["orders"][0]["order_id"] == "ord_alice_1"


@pytest.mark.asyncio
async def test_tool_registry_and_openai_schema():
    registry = ToolRegistry()
    registry.register(QueryOrderTool())
    registry.register(QueryLogisticsTool())

    schemas = registry.get_openai_tools()
    assert len(schemas) == 2
    tool_names = [s["function"]["name"] for s in schemas]
    assert "query_order" in tool_names
    assert "query_logistics" in tool_names

    ctx = SecurityContext(user_id="user_alice")
    exec_res = await registry.execute("query_order", {"order_id": "ord_alice_1"}, context=ctx)
    assert exec_res["success"] is True


@pytest.mark.asyncio
async def test_mcp_adapter():
    async def mock_mcp_handler(params, ctx):
        return {"sku_info": f"SKU-{params['sku_id']} 库存充足"}

    adapter = MCPToolAdapter(
        name="mcp_check_inventory",
        description="Check product inventory via MCP",
        parameters_schema={"type": "object", "properties": {"sku_id": {"type": "string"}}},
        handler=mock_mcp_handler,
    )
    ctx = SecurityContext(user_id="user_alice")
    res = await adapter.execute({"sku_id": "999"}, context=ctx)
    assert "库存充足" in res["sku_info"]

