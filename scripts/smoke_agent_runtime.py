"""Live spike (ADR-0013): self-built AgentRuntime + LiteLLM driving Nature Chat.

Confirms the self-hosted agent loop (no nanobot) holds with a real LLM via LiteLLM —
autonomous multi-turn tool calls + a woven answer. Key from env; never on disk. CN model =
dev smoke only (ADR-0007).

    LLM_API_KEY=ark-... LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 \
        LLM_MODEL=doubao-seed-2-0-pro-260215 python scripts/smoke_agent_runtime.py
"""
from __future__ import annotations

import asyncio
import os


async def main() -> None:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("set LLM_API_KEY (+ LLM_BASE_URL / LLM_MODEL)")
    api_base = os.environ.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.environ.get("LLM_MODEL", "doubao-seed-2-0-pro-260215")

    import litellm

    from birdbot.chat.registry import build_nature_chat_registry
    from birdbot.runtime.agent import AgentRuntime
    from birdbot.tenant.context import TenantEnvelope

    async def completion(*, model, messages, tools):
        # LiteLLM OpenAI-compatible path: openai/<model> + api_base.
        return await litellm.acompletion(
            model=f"openai/{model}",
            messages=messages,
            tools=tools,
            api_base=api_base,
            api_key=api_key,
        )

    runtime = AgentRuntime(model=model, completion=completion)

    envelope = TenantEnvelope(tenant_id="dev", user_id="dev", device_id="dev")
    registry = build_nature_chat_registry(
        envelope=envelope,
        region="US-CA",
        history={"blue tit": {"visits_30d": 8}, "robin": {"visits_30d": 1}},
        rarity={"blue tit": "common", "robin": "rare"},
    )
    history = registry.get("device_history")
    context = registry.get("bird_context")

    answer = await runtime.run(
        prompt="A blue tit just visited my feeder — is it a regular here, and is it special to see one?",
        tools=[history, context],
    )

    print(f"=== AgentRuntime + LiteLLM / {model} ===")
    print("device_history:", history.calls)
    print("bird_context:  ", context.calls)
    print("=== ANSWER ===")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
