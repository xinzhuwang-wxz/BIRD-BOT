"""Model Router (LLM gateway, A5 / ADR-0007).

Business code references only a logical model / capability profile (fast-vision,
deep-reasoning, structured-json); the router resolves it to a concrete backend via a
capability registry (vision / structured-output / prompt-caching / context-window /
pricing / residency region / compliance tags). It asserts required capabilities before
calling (so it never sends a request that would be silently downgraded), validates
structured output after, and enforces the EU data-residency hard constraint (ADR-0007).

It is built ON nanobot's Provider/Preset/Fallback but adds the guardrails the kernel
lacks — notably explicitly rejecting the four unimplemented backends (bedrock,
azure_openai, github_copilot, openai_codex) that the kernel factory would otherwise let
fall through silently to the OpenAI-compatible path.
"""
