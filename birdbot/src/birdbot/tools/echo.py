"""EchoTool — the minimal BirdBot domain tool.

Its only job in S1 is to prove the entry_points plugin seam end-to-end: install the
``birdbot`` package and the kernel's ToolLoader discovers + registers this tool
automatically, with zero edits to ``nanobot/`` (ADR-0001). It echoes its input so a
smoke turn can observe that the kernel actually invoked it.
"""
from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters


@tool_parameters({
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "Text to echo back.",
        },
    },
    "required": [],
})
class EchoTool(Tool):
    """Echo the provided text back to the caller (noop smoke tool)."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return (
            "Echo the provided text back unchanged. Minimal smoke tool used to verify "
            "that BirdBot domain tools are discovered and registered by the kernel."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        text = kwargs.get("text") or ""
        return f"echo: {text}"
