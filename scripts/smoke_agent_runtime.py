"""Live smoke (ADR-0014): AgentRuntime over the governed LLMGateway driving Nature Chat.

Confirms the open-layer agent loop holds with a real LLM through the gateway — autonomous
multi-turn tool calls + a woven answer, with quota/telemetry/routing all governed. Key from
env; never on disk. CN model = dev smoke only (ADR-0007).

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
    from birdbot.chat.tools import dict_rarity, dict_visits
    from birdbot.observability.alerts import ListAlertSink
    from birdbot.observability.telemetry import ListTelemetrySink
    from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
    from birdbot.router.router import ModelRouter
    from birdbot.runtime.agent import AgentRuntime
    from birdbot.runtime.gateway import LLMGateway
    from birdbot.tenant.context import TenantEnvelope

    async def completion(*, model, messages, **kwargs):  # LiteLLM OpenAI-compat path
        return await litellm.acompletion(
            model=f"openai/{model}", messages=messages,
            api_base=api_base, api_key=api_key, **kwargs,
        )

    class _AllowQuota:  # smoke: always allow (production uses RedisQuotaLimiter)
        async def try_acquire(self, key):
            return True

        async def release(self, key):
            pass

    router = ModelRouter(
        CapabilityRegistry([
            ModelEntry(
                logical_name="deep-reasoning", backend="openai_compat", model=model,
                capabilities=frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT}),
                context_window=128_000, pricing_per_mtok=1.0,
                residency_region="CN", compliance_tags=frozenset(),
            )
        ])
    )
    telemetry = ListTelemetrySink()
    gateway = LLMGateway(
        router=router, telemetry=telemetry, alerts=ListAlertSink(),
        quota=_AllowQuota(), completion=completion,
    )
    runtime = AgentRuntime(gateway=gateway, alerts=ListAlertSink())

    envelope = TenantEnvelope(tenant_id="dev", user_id="dev", device_id="dev")
    registry = build_nature_chat_registry(
        envelope=envelope,
        region="US-CA",
        visits=dict_visits({"blue tit": {"visits_30d": 8}, "robin": {"visits_30d": 1}}),
        rarity=dict_rarity({"blue tit": "common", "robin": "rare"}),
    )
    history = registry.get("device_history")
    context = registry.get("bird_context")

    answer = await runtime.run(
        prompt="A blue tit just visited my feeder — is it a regular here, and is it special to see one?",
        tools=[history, context],
        envelope=envelope,
        region="US-CA",
    )

    print(f"=== AgentRuntime + LLMGateway / {model} ===")
    print("device_history:", history.calls)
    print("bird_context:  ", context.calls)
    print("telemetry records:", len(telemetry.records), "(governed by construction)")
    print("=== ANSWER ===")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
