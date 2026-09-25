"""
Deterministic Refund Workflow enforcing hard business rules.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
import uuid
from sqlalchemy import select
from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import Order, OrderStatus, AuditLog, AuditStatus
from newcode.workflow.state import CustomerServiceState


async def execute_refund_workflow(state: CustomerServiceState) -> CustomerServiceState:
    """
    Deterministic rule engine for refund and return:
    1. Check for order_id. If missing -> SUSPEND and ask user to provide order_id.
    2. Query order and enforce user_id ownership (IDOR).
    3. If order status is DELIVERED_OVER_7D or expired -> HARD REJECT (no LLM leniency).
    4. If eligible -> APPROVE, issue refund voucher, set status REFUNDED.
    """
    # 1. Extract order_id from state or query
    order_id = state.order_id
    if not order_id:
        match = re.search(r"ord_[a-zA-Z0-9_]+", state.rewritten_query or state.query)
        if match:
            order_id = match.group(0)

    # If still no order_id, suspend workflow and prompt user
    if not order_id:
        state.is_suspended = True
        state.refund_status = "PENDING_ORDER_ID"
        state.pending_prompt = "请问您需要申请退款的订单号是多少？（例如 ord_1001）"
        state.final_answer = state.pending_prompt
        state.thoughts.append("退款流程中途挂起：缺少必要参数 order_id，向买家发起追问。")
        return state

    # Resume with order_id
    state.order_id = order_id
    state.is_suspended = False

    async with AsyncSessionLocal() as session:
        stmt = select(Order).where(Order.id == order_id)
        order = (await session.execute(stmt)).scalar_one_or_none()

        if not order:
            state.refund_status = "REJECTED_POLICY"
            state.final_answer = f"系统未查询到订单号为 {order_id} 的有效订单，请核对后重新提交。"
            return state

        # IDOR check
        if order.user_id != state.user_id:
            audit = AuditLog(
                user_id=state.user_id,
                action="IDOR_REFUND_ATTEMPT",
                resource_type="order",
                resource_id=order_id,
                status=AuditStatus.BLOCKED,
                details={"owner": order.user_id},
            )
            session.add(audit)
            await session.commit()
            state.refund_status = "REJECTED_POLICY"
            state.final_answer = "抱歉，您无权对非本人账户名下的订单申请退款。"
            return state

        # 3. Check 7-day policy: DELIVERED_OVER_7D
        if order.status in (OrderStatus.DELIVERED_OVER_7D, "DELIVERED_OVER_7D"):
            state.refund_status = "REJECTED_EXPIRED"
            state.final_answer = (
                f"【退款申请驳回】订单 {order_id}（{order.product_name}）签收时间已超过国家法定与平台规定的7天无理由退货期限。"
                "依据商城服务保障条款，超期商品不支持退款申请。如有疑问可联系人工客服协助。"
            )
            state.thoughts.append("触发确定性规则防御：订单签收超过7天，硬规则强制拒绝，禁止随意放行。")
            return state

        if order.status in (OrderStatus.REFUNDED, "REFUNDED"):
            state.refund_status = "REJECTED_POLICY"
            state.final_answer = f"订单 {order_id} 已经是已退款状态，无需重复申请。"
            return state

        # 4. Eligible for refund
        voucher = f"RFV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        order.status = OrderStatus.REFUNDED
        await session.commit()

        state.refund_status = "APPROVED"
        state.refund_voucher = voucher
        state.final_answer = (
            f"【退款申请已受理】您的订单 {order_id}（{order.product_name}，金额 ¥{order.amount:.2f}）已符合全额退款条件。"
            f"系统已为您签发退款凭证编号：{voucher}。退款将在1-3个工作日内原路退回至您的支付账户。"
        )
        state.thoughts.append(f"退款校验通过，生成退款凭证 {voucher}，订单状态已更新为 REFUNDED。")
        return state

