"""Unit tests for the minimal EchoTool.

EchoTool is the smallest possible domain Tool: it exists to prove the entry_points
plugin seam end-to-end (S1). These tests assert its observable behavior as a kernel
``Tool``, not its internals.
"""
from __future__ import annotations

import pytest

from birdbot.tools.echo import EchoTool


def test_echo_tool_is_named_echo():
    assert EchoTool().name == "echo"


@pytest.mark.asyncio
async def test_echo_returns_its_input_text():
    result = await EchoTool().execute(text="chirp")
    assert "chirp" in result


@pytest.mark.asyncio
async def test_echo_handles_missing_text():
    """A noop/smoke tool must not explode when called with no arguments."""
    result = await EchoTool().execute()
    assert isinstance(result, str)
