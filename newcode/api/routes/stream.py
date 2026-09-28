"""Chat streaming and synchronous routes using SSE and standard HTTP."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from newcode.api.auth import AuthenticatedPrincipal, get_current_principal
from newcode.schemas.common import (
    ChatStreamRequest,
    ChatSyncResponse,
    StreamEvent,
    StreamEventType,
)
from newcode.services.runtime import application_services
from newcode.tools.base import IDORForbiddenException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


async def stream_event_generator(
    request_data: ChatStreamRequest,
    principal: AuthenticatedPrincipal,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Generate server-sent events for a chat conversation."""
    try:
        initial_thought = StreamEvent(
            event=StreamEventType.THOUGHT,
            data={
                "thought": "正在执行意图识别与安全业务流程。",
                "content": "正在执行意图识别与安全业务流程。",
            },
        )
        yield ServerSentEvent(
            event=initial_thought.event.value,
            data=initial_thought.to_sse_str(),
        )
        await application_services.initialize()
        state = await application_services.workflow.run(
            user_id=principal.user_id,
            session_id=request_data.session_id,
            query=request_data.query,
        )

        for thought in state.thoughts:
            event = StreamEvent(
                event=StreamEventType.THOUGHT,
                data={"thought": thought, "content": thought},
            )
            yield ServerSentEvent(event=event.event.value, data=event.to_sse_str())

        if state.retrieved_chunks:
            evidence_event = StreamEvent(
                event=StreamEventType.EVIDENCE,
                data=state.retrieved_chunks,
            )
            yield ServerSentEvent(
                event=evidence_event.event.value,
                data=evidence_event.to_sse_str(),
            )

        for start in range(0, len(state.final_answer), 32):
            chunk = state.final_answer[start : start + 32]
            answer_event = StreamEvent(
                event=StreamEventType.ANSWER,
                data={"chunk": chunk, "content": chunk},
            )
            yield ServerSentEvent(
                event=answer_event.event.value,
                data=answer_event.to_sse_str(),
            )

        done_event = StreamEvent(
            event=StreamEventType.DONE,
            data={"status": "completed", "content": "[DONE]"},
        )
        yield ServerSentEvent(
            event=done_event.event.value,
            data=done_event.to_sse_str(),
        )

    except IDORForbiddenException as exc:
        logger.warning("Blocked cross-user resource access: %s", exc)
        error_message = "您无权访问该订单或物流信息。"
        error_event = StreamEvent(
            event=StreamEventType.ERROR,
            data={"error": error_message, "message": error_message},
        )
        yield ServerSentEvent(event=error_event.event.value, data=error_event.to_sse_str())
    except Exception:
        logger.exception("Error during chat streaming")
        error_event = StreamEvent(
            event=StreamEventType.ERROR,
            data={
                "error": "The request could not be completed.",
                "message": "服务暂时不可用，请稍后重试。",
            },
        )
        yield ServerSentEvent(
            event=error_event.event.value,
            data=error_event.to_sse_str(),
        )


@router.post("/api/chat/stream")
@router.post("/chat/stream")
async def chat_stream_post(
    request_payload: ChatStreamRequest,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> EventSourceResponse:
    """POST endpoint for SSE chat stream."""
    _validate_requested_user(request_payload.user_id, principal)
    return EventSourceResponse(
        stream_event_generator(request_payload, principal),
        media_type="text/event-stream",
    )


@router.get("/api/chat/stream")
@router.get("/chat/stream")
async def chat_stream_get(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    user_id: str = Query(..., description="User ID"),
    session_id: str = Query(..., description="Session ID"),
    query: str = Query(..., description="User query message"),
) -> EventSourceResponse:
    """GET endpoint for SSE chat stream with query parameters."""
    _validate_requested_user(user_id, principal)
    req = ChatStreamRequest(
        user_id=user_id,
        session_id=session_id,
        query=query,
        stream=True,
    )
    return EventSourceResponse(
        stream_event_generator(req, principal),
        media_type="text/event-stream",
    )


@router.post("/api/chat/sync", response_model=ChatSyncResponse)
@router.post("/chat/sync", response_model=ChatSyncResponse)
async def chat_sync_post(
    request_payload: ChatStreamRequest,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> ChatSyncResponse:
    """Synchronous chat endpoint returning single unified response."""
    _validate_requested_user(request_payload.user_id, principal)
    await application_services.initialize()
    try:
        state = await application_services.workflow.run(
            user_id=principal.user_id,
            session_id=request_payload.session_id,
            query=request_payload.query,
        )
    except IDORForbiddenException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access that resource.",
        ) from exc
    return ChatSyncResponse(
        user_id=principal.user_id,
        session_id=request_payload.session_id,
        answer=state.final_answer,
        thought="\n".join(state.thoughts) or None,
        evidence=state.retrieved_chunks or None,
    )


def _validate_requested_user(
    requested_user_id: str,
    principal: AuthenticatedPrincipal,
) -> None:
    """Reject attempts to substitute another user's identity in the payload."""
    if requested_user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The request user does not match the authenticated user.",
        )
