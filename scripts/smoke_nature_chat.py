"""Live Nature Chat smoke against a real OpenAI-compatible LLM (key from env).

NOT a test (needs a real key + network) — drives the nanobot agent loop with a real
provider so we can judge the LLM's autonomous tool-selection quality (ADR-0011 next step).
The provider is swappable via env (ADR-0011 "provider backend swappable"); the key is read
from the environment and never written to disk.

    # DeepSeek (text only)
    LLM_PROVIDER=deepseek LLM_API_KEY=sk-... \
        LLM_BASE_URL=https://api.deepseek.com LLM_MODEL=deepseek-chat \
        python scripts/smoke_nature_chat.py

    # Doubao / Volcengine Ark (OpenAI-compatible)
    LLM_PROVIDER=doubao LLM_API_KEY=ark-... \
        LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \
        LLM_MODEL=doubao-seed-2-0-pro-260215 \
        python scripts/smoke_nature_chat.py

DeepSeek and Doubao are CN-residency models: per ADR-0007 they are blocked destinations
for EU/UK user data and are used here only for development smoke (non-EU data). The Model
Router tags them residency_region="CN" and blocks them for EU users.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path


async def main() -> None:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("set LLM_API_KEY (+ optional LLM_BASE_URL / LLM_MODEL / LLM_PROVIDER)")
    provider_name = os.environ.get("LLM_PROVIDER", "deepseek")
    api_base = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    from birdbot.chat.tools import BirdContextTool, DeviceHistoryTool

    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.bus.queue import MessageBus
    from nanobot.config.schema import Config
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider

    # Construct the OpenAI-compatible provider directly so any vendor works regardless of
    # whether the kernel registry knows its name (provider backend swappable, ADR-0011).
    config = Config.model_validate(
        {"agents": {"defaults": {"model": model, "max_tool_iterations": 6}}}
    )
    provider = OpenAICompatProvider(api_key=api_key, api_base=api_base, default_model=model)
    provider.generation = config.resolve_preset().to_generation_settings()

    with tempfile.TemporaryDirectory() as workspace:
        loop = AgentLoop(
            bus=MessageBus(), provider=provider, workspace=Path(workspace), model=model
        )
        history = DeviceHistoryTool({"blue tit": {"visits_30d": 8}, "robin": {"visits_30d": 1}})
        # region is bound deterministically here (would come from the device's
        # post-degradation location), not left for the LLM to fill.
        context = BirdContextTool({"blue tit": "common", "robin": "rare"}, region="US-CA")
        registry = ToolRegistry()
        registry.register(history)
        registry.register(context)

        result = await loop.process_direct(
            "A blue tit just visited my feeder — is it a regular here, "
            "and is it special to see one?",
            tools=registry,
            session_key="tenant:dev:user:dev:device:dev",
        )

    print(f"=== PROVIDER: {provider_name} / {model} ===")
    print("=== TOOLS THE LLM AUTONOMOUSLY CALLED ===")
    print("device_history:", history.calls)
    print("bird_context:  ", context.calls)
    print("=== ANSWER ===")
    print(result.content if result else "(no response)")


if __name__ == "__main__":
    asyncio.run(main())
