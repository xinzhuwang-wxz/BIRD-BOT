"""Model Router (LLM gateway, A5 / ADR-0007).

Business code references only a logical model / capability profile (fast-vision,
deep-reasoning, structured-json); the router resolves it to a concrete backend via a
capability registry (vision / structured-output / prompt-caching / context-window /
pricing / residency region / compliance tags). It asserts required capabilities before
calling (so it never sends a request that would be silently downgraded), validates
structured output after, and enforces the EU data-residency hard constraint (ADR-0007).

Provider resolution runs through the LiteLLM gateway (ADR-0013/0014); the Model Router adds
the guardrails — notably explicitly rejecting the four unimplemented backends (bedrock,
azure_openai, github_copilot, openai_codex) rather than letting them fall through silently to
the OpenAI-compatible path.
"""
