"""
Feedback API route for Thumbs Up / Thumbs Down.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from newcode.api.auth import AuthenticatedPrincipal, get_current_principal
from newcode.models.domain import TriggerType
from newcode.services.problem_pool import ProblemPoolService

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])
problem_pool_service = ProblemPoolService()


class FeedbackRequest(BaseModel):
    user_id: str
    session_id: str
    query: str = Field(..., min_length=1, max_length=10_000)
    answer: str = Field(..., max_length=20_000)
    useful: bool = Field(..., description="True=点赞有用，False=点踩无用")
    comment: str | None = None
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)


@router.post("")
async def submit_feedback(
    req: FeedbackRequest,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
):
    if req.user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The request user does not match the authenticated user.",
        )
    if not req.useful:
        # Negative feedback: automatically ingest into ProblemPool
        problem = await problem_pool_service.add_or_merge_problem(
            session_id=req.session_id,
            trigger_type=TriggerType.USER_THUMBS_DOWN,
            query=req.query,
            rewritten_query=req.query,
            retrieved_chunks=req.retrieved_chunks,
            answer=req.answer,
        )
        return {
            "success": True,
            "message": "已收到您的反馈，已将该条回复推入待优化问题池进行人工校准。",
            "problem_id": problem.id,
            "frequency": problem.frequency,
        }

    return {
        "success": True,
        "message": "非常感谢您的认可与支持！",
    }
