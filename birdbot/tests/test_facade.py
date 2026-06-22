"""Integration tests for the BirdBot thin facade.

The facade wraps ``AgentLoop.from_config`` + ``process_direct`` and must NOT reuse
``Nanobot.run`` (whose per-call ``_extra_hooks`` swap interleaves under multi-tenant
concurrency). These tests drive a real AgentLoop with a scripted fake provider so a
single minimal turn runs end-to-end and the domain tool is actually invoked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from birdbot.agent.facade import BirdBotAgent
from birdbot.tools.echo import EchoTool


class _SpyEcho(EchoTool):
    """EchoTool that records how the kernel invoked it."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return await super().execute(**kwargs)


def _loop_with_scripted_provider(tmp_path, responses):
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat_with_retry = AsyncMock(side_effect=responses)
    return AgentLoop(
        bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model"
    )


@pytest.mark.asyncio
async def test_facade_runs_minimal_turn_and_invokes_tool(tmp_path):
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.providers.base import LLMResponse, ToolCallRequest

    loop = _loop_with_scripted_provider(
        tmp_path,
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(id="c1", name="echo", arguments={"text": "chirp"})
                ],
                usage={},
            ),
            LLMResponse(content="done", tool_calls=[], usage={}),
        ],
    )

    spy = _SpyEcho()
    registry = ToolRegistry()
    registry.register(spy)

    agent = BirdBotAgent(loop)
    result = await agent.process(
        "what's at the feeder?",
        session_key="tenant:t1:user:u1:device:d1",
        tools=registry,
    )

    # The kernel, driven through the thin facade, actually executed our domain tool.
    assert spy.calls == [{"text": "chirp"}]
    assert result is not None
    assert result.content == "done"


@pytest.mark.asyncio
async def test_facade_never_mutates_shared_hook_state(tmp_path):
    """Unlike Nanobot.run, the facade must not swap loop._extra_hooks per call.

    That per-call reassignment interleaves under multi-tenant concurrency, so the
    facade leaves the shared list — identity included — untouched across a turn.
    """
    from nanobot.agent.hook import AgentHook
    from nanobot.providers.base import LLMResponse

    loop = _loop_with_scripted_provider(
        tmp_path, [LLMResponse(content="ok", tool_calls=[], usage={})]
    )
    sentinel = AgentHook()
    original = [sentinel]
    loop._extra_hooks = original

    agent = BirdBotAgent(loop)
    await agent.process("ping", session_key="tenant:t1:user:u1:device:d1")

    assert loop._extra_hooks is original
    assert loop._extra_hooks == [sentinel]


def test_from_config_wires_hooks_at_construction(tmp_path):
    """from_config attaches hooks to the loop once, at construction time."""
    import json

    from nanobot.agent.hook import AgentHook

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "providers": {"openrouter": {"apiKey": "sk-test-key"}},
                "agents": {"defaults": {"model": "openai/gpt-4.1"}},
            }
        )
    )

    hook = AgentHook()
    agent = BirdBotAgent.from_config(config_path, workspace=tmp_path, hooks=[hook])

    assert hook in agent._loop._extra_hooks


def test_from_config_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        BirdBotAgent.from_config("/nonexistent/config.json")
