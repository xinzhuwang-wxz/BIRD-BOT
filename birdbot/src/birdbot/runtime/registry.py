"""Self-hosted ToolRegistry (ADR-0013 / M1): replaces nanobot's ToolRegistry.

Collects tools by name. AgentRuntime executes them directly (``tool.execute``), so this
registry intentionally omits nanobot's execute/prepare_call/cast (which depended on the
kernel Schema validator and the AgentLoop). Stable ``get_definitions`` ordering is kept for
cache-friendly prompts.
"""
from __future__ import annotations

from typing import Any

from birdbot.runtime.tool import Tool


class ToolRegistry:
    """Registry of agent tools, keyed by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def tools(self) -> list[Tool]:
        """All registered tools — pass straight to ``AgentRuntime.run(tools=...)``."""
        return list(self._tools.values())

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_definitions(self) -> list[dict[str, Any]]:
        """OpenAI function schemas, sorted by name for cache-friendly prompts."""
        return sorted(
            (tool.to_schema() for tool in self._tools.values()),
            key=lambda schema: schema["function"]["name"],
        )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
