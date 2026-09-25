"""
MCP (Model Context Protocol) external tool adapter layer.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine
from pydantic import BaseModel
from newcode.tools.base import BaseTool, SecurityContext


class MCPToolAdapter(BaseTool):
    """
    Adapts an external MCP tool definition and execution handler to standard BaseTool.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: type[BaseModel] | dict[str, Any],
        handler: Callable[[dict[str, Any], SecurityContext], Coroutine[Any, Any, dict[str, Any]]],
    ):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.handler = handler

    async def execute(self, params: dict[str, Any], context: SecurityContext) -> dict[str, Any]:
        return await self.handler(params, context)

