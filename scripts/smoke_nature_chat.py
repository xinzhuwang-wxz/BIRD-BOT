"""Live Nature Chat smoke against a real LLM (reads the API key from the environment).

NOT a test (needs a real key + network) — drives the nanobot agent loop with a real
provider so we can judge the LLM's *autonomous tool-selection quality*, the next step
after the fake-provider spike (ADR-0011). The key is read from the env and never written
to disk.

    DEEPSEEK_API_KEY=sk-... python scripts/smoke_nature_chat.py

DeepSeek is a CN-residency model: per ADR-0007 it is a blocked destination for EU/UK user
data and is used here only for development smoke (non-EU data). The Model Router would tag
it residency_region="CN" and block it for EU users.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path


async def main() -> None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("set DEEPSEEK_API_KEY in the environment")

    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.bus.queue import MessageBus
    from nanobot.config.schema import Config
    from nanobot.providers.factory import make_provider

    from birdbot.chat.tools import BirdContextTool, DeviceHistoryTool

    config = Config.model_validate(
        {
            "providers": {"deepseek": {"api_key": key, "api_base": "https://api.deepseek.com"}},
            "agents": {
                "defaults": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "max_tool_iterations": 6,
                }
            },
        }
    )
    provider = make_provider(config)

    with tempfile.TemporaryDirectory() as workspace:
        loop = AgentLoop(
            bus=MessageBus(), provider=provider, workspace=Path(workspace), model="deepseek-chat"
        )
        history = DeviceHistoryTool(
            {"blue tit": {"visits_30d": 8}, "robin": {"visits_30d": 1}}
        )
        context = BirdContextTool({"blue tit": "common", "robin": "rare"})
        registry = ToolRegistry()
        registry.register(history)
        registry.register(context)

        result = await loop.process_direct(
            "A blue tit just visited my feeder — is it a regular here, "
            "and is it special to see one?",
            tools=registry,
            session_key="tenant:dev:user:dev:device:dev",
        )

    print("=== TOOLS THE LLM AUTONOMOUSLY CALLED ===")
    print("device_history:", history.calls)
    print("bird_context:  ", context.calls)
    print("=== ANSWER ===")
    print(result.content if result else "(no response)")


if __name__ == "__main__":
    asyncio.run(main())
