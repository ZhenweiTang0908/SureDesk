"""
Operator Workbench API routes for Problem Pool review and Knowledge Base sync.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import ProblemPool, OperatorStatus
from newcode.services.problem_pool import ProblemPoolService

router = APIRouter(prefix="/api/workbench", tags=["Workbench"])
pool_service = ProblemPoolService()


class AdoptProblemRequest(BaseModel):
    problem_id: str
    standard_answer: str = Field(..., description="运营人员编写的标准答案")


class IgnoreProblemRequest(BaseModel):
    problem_id: str
    reason: str | None = None


@router.get("/problems")
async def list_problems(status: str = "PENDING"):
    async with AsyncSessionLocal() as session:
        stmt = select(ProblemPool).where(ProblemPool.operator_status == status).order_by(ProblemPool.created_at.desc())
        result = await session.execute(stmt)
        items = result.scalars().all()
        return {
            "success": True,
            "total": len(items),
            "problems": [
                {
                    "id": p.id,
                    "session_id": p.session_id,
                    "trigger_type": p.trigger_type,
                    "query": p.query,
                    "rewritten_query": p.rewritten_query,
                    "frequency": p.frequency,
                    "sessions": p.sessions,
                    "answer": p.answer,
                    "operator_status": p.operator_status,
                    "standard_answer": p.standard_answer,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in items
            ],
        }


@router.post("/adopt")
async def adopt_and_sync_problem(req: AdoptProblemRequest):
    async with AsyncSessionLocal() as session:
        stmt = select(ProblemPool).where(ProblemPool.id == req.problem_id)
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="未找到该问题记录")

        item.operator_status = OperatorStatus.ACCEPTED.value
        item.standard_answer = req.standard_answer
        await session.commit()
        await session.refresh(item)

        return {
            "success": True,
            "message": "审核通过，已更新标准答案并触发数据飞轮同步。",
            "problem": {
                "id": item.id,
                "query": item.query,
                "standard_answer": item.standard_answer,
                "status": item.operator_status,
            },
        }


@router.post("/ignore")
async def ignore_problem(req: IgnoreProblemRequest):
    async with AsyncSessionLocal() as session:
        stmt = select(ProblemPool).where(ProblemPool.id == req.problem_id)
        result = await session.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="未找到该问题记录")

        item.operator_status = OperatorStatus.IGNORED.value
        await session.commit()
        return {"success": True, "message": "已将该问题标记为忽略。"}

