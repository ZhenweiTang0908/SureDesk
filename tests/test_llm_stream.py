"""Unit and integration tests for LLM client, structured JSON parsing, and SSE streaming."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from newcode.core.database import init_db
from newcode.core.llm import LLMClient, extract_json_from_text
from newcode.main import app
from newcode.schemas.common import (
    ChatStreamRequest,
    StreamEvent,
    StreamEventType,
)
from newcode.services.runtime import application_services
from tests.auth_helpers import auth_headers


@pytest.fixture(autouse=True)
async def initialize_database():
    """Make API integration tests independent from test execution order."""
    await init_db()


class MockIntentResult(BaseModel):
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Tests for extract_json_from_text and Schema Models
# ---------------------------------------------------------------------------

def test_extract_json_direct():
    raw = '{"intent": "REFUND", "confidence": 0.95, "entities": {"order_id": "123"}}'
    parsed = extract_json_from_text(raw)
    assert parsed["intent"] == "REFUND"
    assert parsed["confidence"] == 0.95
    assert parsed["entities"]["order_id"] == "123"


def test_extract_json_markdown_code_block():
    raw = '''```json
    {
        "intent": "LOGISTICS",
        "confidence": 0.88,
        "entities": {}
    }
    ```'''
    parsed = extract_json_from_text(raw)
    assert parsed["intent"] == "LOGISTICS"
    assert parsed["confidence"] == 0.88


def test_extract_json_plain_code_block():
    raw = '''```
    {
        "intent": "INQUIRY",
        "confidence": 0.72
    }
    ```'''
    parsed = extract_json_from_text(raw)
    assert parsed["intent"] == "INQUIRY"


def test_extract_json_surrounding_prose():
    raw = '''Here is the extracted classification from your query:
    {"intent": "CHAT", "confidence": 0.99, "entities": {}}
    Hope this meets your criteria!'''
    parsed = extract_json_from_text(raw)
    assert parsed["intent"] == "CHAT"
    assert parsed["confidence"] == 0.99


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError, match="No valid JSON found"):
        extract_json_from_text("This text contains no json structures at all.")

    with pytest.raises(ValueError, match="Cannot extract JSON from empty text"):
        extract_json_from_text("   ")


def test_stream_event_schemas():
    # Test enum values and case-insensitivity
    assert StreamEventType("thought") == StreamEventType.THOUGHT
    assert StreamEventType("THOUGHT") == StreamEventType.THOUGHT
    assert StreamEventType.ANSWER.value == "answer"
    assert StreamEventType.DONE.value == "done"

    # Test StreamEvent serialization
    evt_dict = StreamEvent(
        event=StreamEventType.THOUGHT,
        data={"thought": "thinking...", "content": "thinking..."},
    )
    serialized = evt_dict.to_sse_str()
    assert '"thought": "thinking..."' in serialized

    evt_str = StreamEvent(event=StreamEventType.DONE, data="[DONE]")
    assert evt_str.to_sse_str() == "[DONE]"

    # Test ChatStreamRequest defaults
    req = ChatStreamRequest(user_id="u1", session_id="s1", query="hello")
    assert req.stream is True


# ---------------------------------------------------------------------------
# 2. Unit tests for LLMClient methods
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_client_generate_text():
    client = LLMClient()
    mock_choice = MagicMock()
    mock_choice.message.content = "人工客服为您服务"
    mock_response = MagicMock(choices=[mock_choice])

    with patch.object(
        client.client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_create:
        result = await client.generate_text([{"role": "user", "content": "你好"}])
        assert result == "人工客服为您服务"
        mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_client_generate_structured():
    client = LLMClient()
    mock_raw = '''```json
    {
        "intent": "REFUND",
        "confidence": 0.93,
        "entities": {"order_id": "order_1001"}
    }
    ```'''
    mock_choice = MagicMock()
    mock_choice.message.content = mock_raw
    mock_response = MagicMock(choices=[mock_choice])

    with patch.object(
        client.client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result: MockIntentResult = await client.generate_structured(
            messages=[{"role": "user", "content": "我要退款订单 1001"}],
            response_model=MockIntentResult,
        )
        assert isinstance(result, MockIntentResult)
        assert result.intent == "REFUND"
        assert result.confidence == 0.93
        assert result.entities["order_id"] == "order_1001"


@pytest.mark.asyncio
async def test_llm_client_stream_chat():
    client = LLMClient()

    # Mock chunk objects
    def make_chunk(text):
        delta = MagicMock(content=text)
        choice = MagicMock(delta=delta)
        return MagicMock(choices=[choice])

    async def mock_async_stream(*args, **kwargs):
        for token in ["正在", "查询", "您的", "物流"]:
            yield make_chunk(token)

    with patch.object(
        client.client.chat.completions,
        "create",
        side_effect=mock_async_stream,
    ):
        tokens = []
        async for chunk in client.stream_chat([{"role": "user", "content": "查物流"}]):
            tokens.append(chunk)
        assert tokens == ["正在", "查询", "您的", "物流"]


# ---------------------------------------------------------------------------
# 3. Integration tests for FastAPI endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_chat_sync():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "user_id": "buyer_01",
            "session_id": "sess_01",
            "query": "你好",
        }
        resp = await ac.post(
            "/api/chat/sync",
            json=payload,
            headers=auth_headers("buyer_01"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "buyer_01"
        assert data["session_id"] == "sess_01"
        assert "SureDesk" in data["answer"]
        assert data["thought"] is not None


@pytest.mark.asyncio
async def test_api_chat_stream_post_sse():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "user_id": "buyer_02",
            "session_id": "sess_02",
            "query": "你好",
        }
        async with ac.stream(
            "POST",
            "/api/chat/stream",
            json=payload,
            headers=auth_headers("buyer_02"),
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            events = []
            current_event = None
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("event:"):
                    current_event = line.replace("event:", "").strip()
                elif line.startswith("data:"):
                    data_str = line.replace("data:", "").strip()
                    events.append((current_event, data_str))

            event_types = [event[0] for event in events]
            assert event_types[0] == StreamEventType.THOUGHT.value
            assert StreamEventType.ANSWER.value in event_types
            assert event_types[-1] == StreamEventType.DONE.value

            answer_chunks = [
                json.loads(event[1])["content"]
                for event in events
                if event[0] == StreamEventType.ANSWER.value
            ]
            assert "SureDesk" in "".join(answer_chunks)


@pytest.mark.asyncio
async def test_api_chat_stream_get_sse():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        params = {
            "user_id": "buyer_03",
            "session_id": "sess_03",
            "query": "查物流",
        }
        async with ac.stream(
            "GET",
            "/api/chat/stream",
            params=params,
            headers=auth_headers("buyer_03"),
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            events = []
            current_event = None
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("event:"):
                    current_event = line.replace("event:", "").strip()
                elif line.startswith("data:"):
                    events.append((current_event, line.replace("data:", "").strip()))

            event_types = [event[0] for event in events]
            assert StreamEventType.THOUGHT.value in event_types
            assert StreamEventType.ANSWER.value in event_types
            assert StreamEventType.DONE.value in event_types


@pytest.mark.asyncio
async def test_api_chat_stream_error_handling():
    with patch.object(
        application_services.workflow,
        "run",
        new_callable=AsyncMock,
        side_effect=RuntimeError("sensitive upstream detail"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {
                "user_id": "buyer_err",
                "session_id": "sess_err",
                "query": "测试异常",
            }
            async with ac.stream(
                "POST",
                "/api/chat/stream",
                json=payload,
                headers=auth_headers("buyer_err"),
            ) as resp:
                assert resp.status_code == 200
                events = []
                current_event = None
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("event:"):
                        current_event = line.replace("event:", "").strip()
                    elif line.startswith("data:"):
                        events.append((current_event, line.replace("data:", "").strip()))

                event_types = [e[0] for e in events]
                assert StreamEventType.ERROR.value in event_types
                error_entry = next(e for e in events if e[0] == StreamEventType.ERROR.value)
                error_data = json.loads(error_entry[1])
                assert error_data["error"] == "The request could not be completed."
                assert "sensitive upstream detail" not in json.dumps(error_data)


@pytest.mark.asyncio
async def test_health_check_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "SureDesk" in data["app"]
