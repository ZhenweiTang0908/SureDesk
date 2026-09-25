"""
Base Tool class and Security Context for IDOR protection.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel


@dataclass
class SecurityContext:
    user_id: str
    session_id: str = "default_session"
    ip: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class IDORForbiddenException(Exception):
    """Raised when an operation attempts unauthorized access across user boundary."""
    def __init__(self, message: str = "越权访问被拦截：无权查看非本人订单或物流信息"):
        super().__init__(message)
        self.message = message


class BaseTool(ABC):
    name: str
    description: str
    parameters_schema: type[BaseModel] | dict[str, Any]

    @abstractmethod
    async def execute(self, params: dict[str, Any], context: SecurityContext) -> dict[str, Any]:
        """Execute the tool within the verified security context."""
        pass

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert tool to OpenAI Function Calling format."""
        if hasattr(self.parameters_schema, "model_json_schema"):
            schema = self.parameters_schema.model_json_schema()
        else:
            schema = self.parameters_schema
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

