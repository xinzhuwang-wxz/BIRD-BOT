"""M1 (ADR-0013): self-hosted Tool protocol + ToolRegistry replace nanobot's."""
from __future__ import annotations

import pytest

from birdbot.runtime.registry import ToolRegistry
from birdbot.runtime.tool import Tool, tool_parameters


@tool_parameters(
    {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
)
class _Probe(Tool):
    @property
    def name(self) -> str:
        return "probe"

    @property
    def description(self) -> str:
        return "probe tool"

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs):
        return f"got {kwargs.get('x')}"


def test_tool_parameters_returns_fresh_copy_each_access():
    tool = _Probe()
    assert tool.parameters["properties"]["x"]["type"] == "string"
    tool.parameters["properties"]["x"]["type"] = "mutated"  # mutate the returned dict
    assert tool.parameters["properties"]["x"]["type"] == "string"  # next access is pristine


def test_tool_to_schema_is_openai_function_format():
    assert _Probe().to_schema() == {
        "type": "function",
        "function": {
            "name": "probe",
            "description": "probe tool",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        },
    }


@pytest.mark.asyncio
async def test_tool_executes():
    assert await _Probe().execute(x="hi") == "got hi"


def test_registry_register_get_has_tools():
    registry = ToolRegistry()
    probe = _Probe()
    registry.register(probe)

    assert registry.has("probe")
    assert registry.get("probe") is probe
    assert "probe" in registry
    assert len(registry) == 1
    assert registry.tools() == [probe]
    assert registry.tool_names == ["probe"]
    assert registry.get("missing") is None


def test_registry_get_definitions_sorted_by_name():
    class _Other(_Probe):
        @property
        def name(self) -> str:
            return "aardvark"

    registry = ToolRegistry()
    registry.register(_Probe())
    registry.register(_Other())

    names = [d["function"]["name"] for d in registry.get_definitions()]
    assert names == ["aardvark", "probe"]  # stable sorted prefix
