"""Unified LLM client wrapper supporting chat completions, structured output, and streaming."""

from collections.abc import AsyncGenerator
import inspect
import json
import re
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from newcode.core.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


def extract_json_from_text(text: str) -> Any:
    """Robustly extract JSON data from text, handling markdown code fences and surrounding prose.

    Args:
        text: Raw text string potentially containing JSON.

    Returns:
        Parsed JSON object (dict or list).

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    if not text or not text.strip():
        raise ValueError("Cannot extract JSON from empty text")

    cleaned = text.strip()

    # 1. Match code blocks ```json ... ``` or ``` ... ```
    code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    matches = re.findall(code_block_pattern, cleaned, re.IGNORECASE)
    for candidate in matches:
        candidate = candidate.strip()
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 2. Try parsing the full stripped text directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Find outermost curly braces { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 4. Find outermost square brackets [ ... ]
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket > first_bracket:
        candidate = cleaned[first_bracket : last_bracket + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in response: {text[:200]}")


class LLMClient:
    """Asynchronous OpenAI-compatible LLM client wrapper."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        settings: Settings | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        resolved_base_url = base_url or resolved_settings.OPENAI_API_BASE
        resolved_api_key = api_key or resolved_settings.OPENAI_API_KEY or "dummy_key"

        self.client: AsyncOpenAI = client or AsyncOpenAI(
            base_url=resolved_base_url,
            api_key=resolved_api_key,
        )
        self.default_model: str = default_model or resolved_settings.OPENAI_MODEL

    async def generate_text(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate non-streaming text completion from a chat prompt."""
        response = await self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return choice.message.content or ""

    async def generate_structured(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate a structured Pydantic model response with robust JSON extraction."""
        schema_str = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        instruction = (
            f"Please reply with a valid JSON object strictly conforming to this schema:\n"
            f"```json\n{schema_str}\n```\n"
            "Do not include any introductory or concluding text outside the JSON object."
        )

        augmented_messages: list[dict[str, Any]] = []
        has_system = False
        for msg in messages:
            if msg.get("role") == "system":
                has_system = True
                augmented_messages.append({
                    **msg,
                    "content": f"{msg.get('content', '')}\n\n{instruction}",
                })
            else:
                augmented_messages.append(dict(msg))

        if not has_system:
            augmented_messages.insert(0, {"role": "system", "content": instruction})

        raw_response = await self.generate_text(
            messages=augmented_messages,
            model=model,
            temperature=temperature,
            max_tokens=2048,
        )

        parsed_json = extract_json_from_text(raw_response)
        return response_model.model_validate(parsed_json)

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion chunks asynchronously."""
        response = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        if inspect.isawaitable(response):
            response_stream = await response
        else:
            response_stream = response
        async for chunk in response_stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content


_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create singleton LLMClient instance."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


async def generate_text(
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """Module-level helper to generate text using the default LLM client."""
    client = get_llm_client()
    return await client.generate_text(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def generate_structured(
    messages: list[dict[str, Any]],
    response_model: type[T],
    model: str | None = None,
    temperature: float = 0.1,
) -> T:
    """Module-level helper to generate structured output using the default LLM client."""
    client = get_llm_client()
    return await client.generate_structured(
        messages=messages,
        response_model=response_model,
        model=model,
        temperature=temperature,
    )


async def stream_chat(
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """Module-level helper to stream chat chunks using the default LLM client."""
    client = get_llm_client()
    async for chunk in client.stream_chat(
        messages=messages,
        model=model,
        temperature=temperature,
    ):
        yield chunk
