"""
Unit tests for CustomerServiceWorkflow, deterministic refund state machine, suspension, and agent node.
"""
import pytest
from sqlalchemy import delete
from newcode.core.database import init_db, AsyncSessionLocal
from newcode.models.domain import User, Order, OrderStatus
from newcode.rag.engine import HybridRetrievalEngine
from newcode.workflow.graph import CustomerServiceWorkflow

SAMPLE_POLICY = """# 商城售后政策
## 7天无理由退货
自商品签收之日起7日内，在保证商品完好的前提下支持退货。
"""

@pytest.fixture(autouse=True)
async def setup_db_for_workflow():
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Order).where(Order.id.in_(["ord_wf_1", "ord_wf_expired"])))
        await session.execute(delete(User).where(User.id == "user_wf_buyer"))
        await session.commit()

        u = User(id="user_wf_buyer", username="wf_buyer", role="BUYER")
        session.add(u)

        # 1. Eligible order (PAID_UNSHIPPED)
        o1 = Order(
            id="ord_wf_1",
            user_id="user_wf_buyer",
            status=OrderStatus.PAID_UNSHIPPED,
            amount=199.0,
            product_name="便携式蓝牙音箱",
        )
        # 2. Expired order (DELIVERED_OVER_7D)
        o2 = Order(
            id="ord_wf_expired",
            user_id="user_wf_buyer",
            status=OrderStatus.DELIVERED_OVER_7D,
            amount=899.0,
            product_name="智能扫地机器人",
        )
        session.add_all([o1, o2])
        await session.commit()


@pytest.mark.asyncio
async def test_refund_workflow_suspension_and_resume():
    engine = HybridRetrievalEngine()
    engine.add_markdown_document(SAMPLE_POLICY)
    workflow = CustomerServiceWorkflow(rag_engine=engine)

    # Turn 1: User asks for refund without specifying order_id
    state1 = await workflow.run(
        user_id="user_wf_buyer",
        session_id="sess_refund_test",
        query="我想申请退款",
    )
    assert state1.is_suspended is True
    assert state1.refund_status == "PENDING_ORDER_ID"
    assert "订单号" in state1.final_answer

    # Turn 2: User provides order_id to resume
    state2 = await workflow.run(
        user_id="user_wf_buyer",
        session_id="sess_refund_test",
        query="我的订单号是 ord_wf_1",
    )
    assert state2.is_suspended is False
    assert state2.refund_status == "APPROVED"
    assert "退款凭证编号" in state2.final_answer
    assert state2.refund_voucher.startswith("RFV-")


@pytest.mark.asyncio
async def test_refund_expired_order_hard_rejection():
    workflow = CustomerServiceWorkflow()

    # User directly asks to refund expired order
    state = await workflow.run(
        user_id="user_wf_buyer",
        session_id="sess_expired_test",
        query="退款 ord_wf_expired",
    )
    assert state.refund_status == "REJECTED_EXPIRED"
    assert "已超过国家法定与平台规定的7天无理由退货期限" in state.final_answer


@pytest.mark.asyncio
async def test_chitchat_and_complaint_routing():
    workflow = CustomerServiceWorkflow()

    # Chitchat
    res_chat = await workflow.run(
        user_id="user_wf_buyer",
        session_id="sess_chat",
        query="你好呀",
    )
    assert "MewHelp" in res_chat.final_answer

    # Complaint
    res_complaint = await workflow.run(
        user_id="user_wf_buyer",
        session_id="sess_complaint",
        query="态度太恶劣了，我要找人工客服投诉！",
    )
    assert "加急工单" in res_complaint.final_answer or "人工客服" in res_complaint.final_answer


@pytest.mark.asyncio
async def test_rag_knowledge_answering():
    engine = HybridRetrievalEngine()
    engine.add_markdown_document(SAMPLE_POLICY)
    workflow = CustomerServiceWorkflow(rag_engine=engine)

    res = await workflow.run(
        user_id="user_wf_buyer",
        session_id="sess_rag",
        query="7天无理由退货的要求是什么？",
    )
    assert "7日内" in res.final_answer
    assert "【依据政策来源】" in res.final_answer

