"""Smoke test: installing birdbot makes the kernel auto-discover + register its tools.

This pins the entry_points plugin seam (group="nanobot.tools"), which had zero
landings and zero coverage in the base kernel before S1. The point is to prove the
"install the package -> the kernel finds the tool" path with no edits to nanobot/.
"""
from __future__ import annotations

from importlib.metadata import entry_points

from birdbot.tools.echo import EchoTool


def test_echo_entry_point_is_published():
    """The installed birdbot distribution publishes EchoTool under nanobot.tools."""
    eps = {ep.name: ep.value for ep in entry_points(group="nanobot.tools")}
    assert eps.get("birdbot_echo") == "birdbot.tools.echo:EchoTool"


def test_kernel_loader_registers_echo(tmp_path):
    """The kernel's real ToolLoader.load path discovers + registers echo — no kernel edits."""
    from nanobot.agent.tools.context import ToolContext
    from nanobot.agent.tools.loader import ToolLoader
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.config.schema import Config

    registry = ToolRegistry()
    ctx = ToolContext(config=Config().tools, workspace=str(tmp_path))
    registered = ToolLoader().load(ctx, registry)

    assert "echo" in registered
    assert registry.has("echo")
    assert isinstance(registry.get("echo"), EchoTool)
