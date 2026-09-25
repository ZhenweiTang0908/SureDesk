"""Chat streaming and synchronous routes using SSE and standard HTTP."""

from collections.abc import AsyncGenerator
import json
import logging
from typing import Any

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from newcode.core.llm import get_llm_client
from newcode.schemas.common import (
    ChatStreamRequest,
    ChatSyncResponse,
    StreamEvent,
    StreamEventType,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


async def stream_event_generator(
    request_data: ChatStreamRequest,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Generate server-sent events for a chat conversation."""
    client = get_llm_client()

    try:
        # 1. Emit THOUGHT event
        thought_data = {
            "thought": "正在分析用户意图并准备回复...",
            "content": "正在分析用户意图并准备回复...",
        }
        thought_event = StreamEvent(
            event=StreamEventType.THOUGHT,
            data=thought_data,
        )
        yield ServerSentEvent(
            event=thought_event.event.value,
            data=thought_event.to_sse_str(),
        )

        # 2. Build messages and stream ANSWER chunks
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个电商平台的智能客服小助手，请以友善、专业、耐心的语气解答用户的咨询与售后问题。"
                ),
            },
            {"role": "user", "content": request_data.query},
        ]

        async for chunk in client.stream_chat(messages):
            answer_event = StreamEvent(
                event=StreamEventType.ANSWER,
                data={"chunk": chunk, "content": chunk},
            )
            yield ServerSentEvent(
                event=answer_event.event.value,
                data=answer_event.to_sse_str(),
            )

        # 3. Emit DONE event
        done_event = StreamEvent(
            event=StreamEventType.DONE,
            data={"status": "completed", "content": "[DONE]"},
        )
        yield ServerSentEvent(
            event=done_event.event.value,
            data=done_event.to_sse_str(),
        )

    except Exception as exc:
        logger.exception("Error during chat streaming: %s", exc)
        error_event = StreamEvent(
            event=StreamEventType.ERROR,
            data={"error": str(exc), "message": str(exc)},
        )
        yield ServerSentEvent(
            event=error_event.event.value,
            data=error_event.to_sse_str(),
        )


@router.post("/api/chat/stream")
@router.post("/chat/stream")
async def chat_stream_post(request_payload: ChatStreamRequest) -> EventSourceResponse:
    """POST endpoint for SSE chat stream."""
    return EventSourceResponse(
        stream_event_generator(request_payload),
        media_type="text/event-stream",
    )


@router.get("/api/chat/stream")
@router.get("/chat/stream")
async def chat_stream_get(
    user_id: str = Query(..., description="User ID"),
    session_id: str = Query(..., description="Session ID"),
    query: str = Query(..., description="User query message"),
) -> EventSourceResponse:
    """GET endpoint for SSE chat stream with query parameters."""
    req = ChatStreamRequest(
        user_id=user_id,
        session_id=session_id,
        query=query,
        stream=True,
    )
    return EventSourceResponse(
        stream_event_generator(req),
        media_type="text/event-stream",
    )


@router.post("/api/chat/sync", response_model=ChatSyncResponse)
@router.post("/chat/sync", response_model=ChatSyncResponse)
async def chat_sync_post(request_payload: ChatStreamRequest) -> ChatSyncResponse:
    """Synchronous chat endpoint returning single unified response."""
    client = get_llm_client()
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个电商平台的智能客服小助手，请以友善、专业、耐心的语气解答用户的咨询与售后问题。"
            ),
        },
        {"role": "user", "content": request_payload.query},
    ]
    answer = await client.generate_text(messages)
    return ChatSyncResponse(
        user_id=request_payload.user_id,
        session_id=request_payload.session_id,
        answer=answer,
        thought="意图识别与回答生成完成",
        evidence=None,
    )
