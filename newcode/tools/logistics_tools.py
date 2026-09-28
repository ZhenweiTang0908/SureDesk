"""
Logistics query tools with IDOR protection.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import AuditLog, AuditStatus, Logistics
from newcode.tools.base import BaseTool, IDORForbiddenException, SecurityContext


class QueryLogisticsParams(BaseModel):
    order_id: str = Field(..., description="关联订单号，如 ord_1001")


class QueryLogisticsTool(BaseTool):
    name = "query_logistics"
    description = "根据订单号查询对应的包裹物流轨迹、承运快递公司及当前签收状态。"
    parameters_schema = QueryLogisticsParams

    async def execute(self, params: dict[str, Any], context: SecurityContext) -> dict[str, Any]:
        validated = QueryLogisticsParams(**params)
        order_id = validated.order_id

        async with AsyncSessionLocal() as session:
            stmt = select(Logistics).where(Logistics.order_id == order_id)
            result = await session.execute(stmt)
            logistics = result.scalar_one_or_none()

            if not logistics:
                return {
                    "success": False,
                    "error": f"暂未查询到订单 {order_id} 的物流运单记录。",
                }

            # IDOR check
            if logistics.user_id != context.user_id:
                audit = AuditLog(
                    user_id=context.user_id,
                    action="IDOR_QUERY_LOGISTICS_ATTEMPT",
                    resource_type="logistics",
                    resource_id=order_id,
                    status=AuditStatus.BLOCKED,
                    details={
                        "target_owner": logistics.user_id,
                        "session_id": context.session_id,
                    },
                )
                session.add(audit)
                await session.commit()
                raise IDORForbiddenException(f"越权访问拦截：您无权查询订单 {order_id} 的物流轨迹。")

            return {
                "success": True,
                "logistics": {
                    "order_id": logistics.order_id,
                    "tracking_number": logistics.tracking_number,
                    "carrier": logistics.carrier,
                    "status": logistics.status.value if hasattr(logistics.status, "value") else str(logistics.status),
                    "traces": logistics.traces,
                    "updated_at": logistics.updated_at.isoformat() if logistics.updated_at else None,
                },
            }
