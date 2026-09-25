"""Common schemas for requests, responses, and SSE event streaming."""

from enum import Enum
import json
from typing import Any, Union
from pydantic import BaseModel, ConfigDict, Field


class StreamEventType(str, Enum):
    """Event types supported in server-sent events (SSE) chat stream."""

    THOUGHT = "thought"
    ANSWER = "answer"
    EVIDENCE = "evidence"
    ERROR = "error"
    DONE = "done"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower() or member.name.lower() == value.lower():
                    return member
        return None


class StreamEvent(BaseModel):
    """Data transfer object for a single SSE event."""

    event: StreamEventType = Field(
        ...,
        description="Type of the stream event (thought, answer, evidence, error, done)",
    )
    data: Union[dict[str, Any], list[Any], str] = Field(
        ...,
        description="Payload of the event, either structured dict/list or plain string",
    )

    model_config = ConfigDict(use_enum_values=False)

    def to_sse_str(self) -> str:
        """Convert payload to string suitable for SSE data field."""
        if isinstance(self.data, (dict, list)):
            return json.dumps(self.data, ensure_ascii=False)
        return str(self.data)


class ChatStreamRequest(BaseModel):
    """Request payload for streaming or synchronous chat."""

    user_id: str = Field(
        ...,
        description="Unique identifier for the user initiating the request",
        examples=["user_buyer_1"],
    )
    session_id: str = Field(
        ...,
        description="Conversation session identifier",
        examples=["session_1001"],
    )
    query: str = Field(
        ...,
        description="User message or question",
        examples=["我买的机械键盘发货了吗？"],
    )
    stream: bool = Field(
        default=True,
        description="Whether to return a streaming SSE response",
    )


class ChatSyncResponse(BaseModel):
    """Response payload for synchronous (non-streaming) chat endpoint."""

    user_id: str = Field(..., description="User ID")
    session_id: str = Field(..., description="Session ID")
    answer: str = Field(..., description="Assistant answer content")
    thought: str | None = Field(default=None, description="Internal reasoning or thoughts")
    evidence: list[dict[str, Any]] | None = Field(
        default=None,
        description="Evidence or retrieved knowledge chunks used to answer",
    )

