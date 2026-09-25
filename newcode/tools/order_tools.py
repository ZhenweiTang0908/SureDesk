"""
Order query tools with strict row-level security and IDOR protection.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import select
from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import Order, AuditLog, AuditStatus
from newcode.tools.base import BaseTool, SecurityContext, IDORForbiddenException


class QueryOrderParams(BaseModel):
    order_id: str = Field(..., description="订单号，如 ord_1001")


class QueryOrderTool(BaseTool):
    name = "query_order"
    description = "查询订单详情，包含商品名称、实付金额、支付时间及订单状态。"
    parameters_schema = QueryOrderParams

    async def execute(self, params: dict[str, Any], context: SecurityContext) -> dict[str, Any]:
        validated = QueryOrderParams(**params)
        order_id = validated.order_id

        async with AsyncSessionLocal() as session:
            # 1. Search for order across DB
            stmt = select(Order).where(Order.id == order_id)
            result = await session.execute(stmt)
            order = result.scalar_one_or_none()

            if not order:
                return {
                    "success": False,
                    "error": f"未查询到订单号为 {order_id} 的订单，请核实订单号。",
                }

            # 2. Strict IDOR verification: Check if order belongs to current authenticated user
            if order.user_id != context.user_id:
                # Log security violation in AuditLog
                audit = AuditLog(
                    user_id=context.user_id,
                    action="IDOR_QUERY_ORDER_ATTEMPT",
                    resource_type="order",
                    resource_id=order_id,
                    status=AuditStatus.BLOCKED,
                    details={
                        "target_owner": order.user_id,
                        "session_id": context.session_id,
                        "ip": context.ip,
                    },
                )
                session.add(audit)
                await session.commit()
                raise IDORForbiddenException(f"越权访问拦截：您无权查询订单 {order_id}，该行为已记入安全审计日志。")

            return {
                "success": True,
                "order": {
                    "order_id": order.id,
                    "product_name": order.product_name,
                    "amount": float(order.amount),
                    "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                    "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                },
            }


class ListOrdersTool(BaseTool):
    name = "list_user_orders"
    description = "获取当前登录用户的所有历史订单列表。"
    parameters_schema = {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: SecurityContext) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            stmt = select(Order).where(Order.user_id == context.user_id)
            result = await session.execute(stmt)
            orders = result.scalars().all()
            return {
                "success": True,
                "total": len(orders),
                "orders": [
                    {
                        "order_id": o.id,
                        "product_name": o.product_name,
                        "amount": float(o.amount),
                        "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                    }
                    for o in orders
                ],
            }

