"""
Tool Registry with timeout management, schema generation, and execution audit.
"""
from __future__ import annotations

import asyncio
from typing import Any
from newcode.core.database import AsyncSessionLocal
from newcode.models.domain import AuditLog, AuditStatus
from newcode.tools.base import BaseTool, SecurityContext, IDORForbiddenException


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        return self.tools.get(name)

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self.tools.values()]

    async def execute(
        self,
        name: str,
        params: dict[str, Any],
        context: SecurityContext,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        tool = self.get_tool(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' not found in registry."}

        try:
            result = await asyncio.wait_for(
                tool.execute(params, context),
                timeout=timeout_seconds,
            )

            # Record successful tool call
            async with AsyncSessionLocal() as session:
                audit = AuditLog(
                    user_id=context.user_id,
                    action=f"TOOL_CALL_{name.upper()}",
                    resource_type="tool",
                    resource_id=name,
                    status=AuditStatus.ALLOWED,
                    details={"params": params},
                )
                session.add(audit)
                await session.commit()

            return result

        except IDORForbiddenException:
            # Re-raise IDOR exception so caller handles permission fault
            raise
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Tool execution timed out after {timeout_seconds}s."}
        except Exception as e:
            return {"success": False, "error": f"Tool execution error: {str(e)}"}

